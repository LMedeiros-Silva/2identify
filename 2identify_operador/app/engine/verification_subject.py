"""Who a release verification is about: exactly one reliably observed person.

PPE boxes are per-frame observations with no owner. Before they feed the stability
window they must belong to the person being released: frames with nobody, with
several people, or with an unreliable skeleton never count as evidence, and boxes
outside that person's body region are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.engine.helmet_placement import person_geometry
from app.vision.pose import PersonPose, PoseDetectionBatch
from app.vision.ppe import PpeDetectionBatch

_PERSON_CONFIDENCE = 0.5
_KEYPOINT_CONFIDENCE = 0.5
# Margins in shoulder widths: arms and sleeves to the sides, helmet above the head.
_SIDE_MARGIN = 0.75
_TOP_MARGIN = 1.0


class SubjectIssue(StrEnum):
    SEM_POSE = "sem_pose"
    NENHUMA_PESSOA = "nenhuma_pessoa"
    VARIAS_PESSOAS = "varias_pessoas"
    PESSOA_INCERTA = "pessoa_incerta"


@dataclass(frozen=True, slots=True)
class VerificationSubject:
    issue: SubjectIssue | None
    people: int = 0
    region: tuple[float, float, float, float] | None = None

    @property
    def identified(self) -> bool:
        return self.issue is None


def identify_subject(
    batch: PpeDetectionBatch,
    pose: PoseDetectionBatch | None,
) -> VerificationSubject:
    if pose is None or (pose.frame_width, pose.frame_height) != (
        batch.frame_width,
        batch.frame_height,
    ):
        return VerificationSubject(SubjectIssue.SEM_POSE)
    people = tuple(item for item in pose.poses if item.confidence >= _PERSON_CONFIDENCE)
    if not people:
        return VerificationSubject(SubjectIssue.NENHUMA_PESSOA)
    if len(people) > 1:
        return VerificationSubject(SubjectIssue.VARIAS_PESSOAS, people=len(people))
    region = _body_region(people[0], batch.frame_height)
    if region is None:
        return VerificationSubject(SubjectIssue.PESSOA_INCERTA, people=1)
    return VerificationSubject(None, people=1, region=region)


def subject_detections(
    batch: PpeDetectionBatch,
    subject: VerificationSubject,
) -> PpeDetectionBatch:
    """Keep only boxes centered on the identified person; nothing without one."""

    region = subject.region
    detections = ()
    if region is not None:
        x1, y1, x2, y2 = region
        detections = tuple(
            item
            for item in batch.detections
            if x1 <= (item.box.x1 + item.box.x2) / 2 <= x2
            and y1 <= (item.box.y1 + item.box.y2) / 2 <= y2
        )
    return PpeDetectionBatch(
        detections,
        batch.frame_width,
        batch.frame_height,
        batch.inference_milliseconds,
        camera_id=batch.camera_id,
        generation=batch.generation,
        captured_at=batch.captured_at,
    )


def _body_region(
    person: PersonPose,
    frame_height: int,
) -> tuple[float, float, float, float] | None:
    geometry = person_geometry(person)
    if geometry is None:
        return None
    _head, shoulder_width = geometry
    points = [
        (item.x, item.y) for item in person.keypoints if item.confidence >= _KEYPOINT_CONFIDENCE
    ]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (
        min(xs) - _SIDE_MARGIN * shoulder_width,
        min(ys) - _TOP_MARGIN * shoulder_width,
        max(xs) + _SIDE_MARGIN * shoulder_width,
        # Legs and boots continue below the last visible joint.
        float(frame_height),
    )
