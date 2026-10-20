"""Conservative helmet placement using a person's own COCO landmarks."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module

import pytest

from app.domain.operation import Operation, PpeRequirement
from app.engine.ppe_safety import PpeSafetyEngine, PpeSafetyStatus
from app.engine.ppe_stability import PpeStabilityEngine
from app.vision.pose import (
    COCO_KEYPOINT_COUNT,
    CocoKeypoint,
    PersonPose,
    PoseDetectionBatch,
    PoseKeypoint,
)
from app.vision.ppe import DetectionBox, PpeDetection, PpeDetectionBatch


def _helmet(box: tuple[float, float, float, float]) -> PpeDetection:
    return PpeDetection(1, "capacete", 0.94, DetectionBox(*box))


def _person(
    offset: float = 0, *, low_confidence: bool = False, incomplete: bool = False
) -> PersonPose:
    points = [PoseKeypoint(0, 0, 0) for _ in range(COCO_KEYPOINT_COUNT)]
    confidence = 0.2 if low_confidence else 0.95
    positions = {
        CocoKeypoint.NOSE: (100, 60),
        CocoKeypoint.LEFT_EYE: (94, 55),
        CocoKeypoint.RIGHT_EYE: (106, 55),
        CocoKeypoint.LEFT_EAR: (88, 60),
        CocoKeypoint.RIGHT_EAR: (112, 60),
        CocoKeypoint.LEFT_SHOULDER: (80, 100),
        CocoKeypoint.RIGHT_SHOULDER: (120, 100),
        CocoKeypoint.LEFT_ELBOW: (78, 140),
        CocoKeypoint.RIGHT_ELBOW: (122, 140),
        CocoKeypoint.LEFT_WRIST: (75, 180),
        CocoKeypoint.RIGHT_WRIST: (125, 180),
        CocoKeypoint.LEFT_HIP: (85, 220),
        CocoKeypoint.RIGHT_HIP: (115, 220),
    }
    if incomplete:
        positions = {CocoKeypoint.NOSE: (100, 60)}
    for key, (x, y) in positions.items():
        points[int(key)] = PoseKeypoint(x + offset, y, confidence)
    return PersonPose(0.95, tuple(points))


def _batch(
    camera_id: int,
    helmets: tuple[PpeDetection, ...],
    people: tuple[PersonPose, ...],
) -> tuple[PpeDetectionBatch, PoseDetectionBatch]:
    timestamp = datetime.now(UTC)
    return (
        PpeDetectionBatch(helmets, 640, 480, 1, camera_id, 1, timestamp),
        PoseDetectionBatch(people, 640, 480, 1, camera_id, 1, timestamp),
    )


@pytest.mark.parametrize(
    ("box", "expected"),
    [
        ((85, 25, 115, 60), "NA_CABECA"),
        ((60, 165, 85, 190), "NA_MAO"),
        ((115, 165, 140, 190), "NA_MAO"),
        ((300, 300, 330, 330), "INDETERMINADO"),
    ],
)
def test_helmet_uses_head_or_either_hand_of_the_same_person(box, expected) -> None:
    module = import_module("app.engine.helmet_placement")
    assert module.classify_helmet(_helmet(box), _person()).name == expected


@pytest.mark.parametrize("person", [_person(incomplete=True), _person(low_confidence=True)])
def test_incomplete_or_unreliable_pose_is_indeterminate(person) -> None:
    module = import_module("app.engine.helmet_placement")
    assert module.classify_helmet(_helmet((85, 25, 115, 60)), person).name == "INDETERMINADO"


def test_two_people_and_two_helmets_keep_their_own_identity() -> None:
    module = import_module("app.engine.helmet_placement")
    engine = module.HelmetPlacementEngine(stability_frames=2)
    ppe, pose = _batch(
        7,
        (_helmet((85, 25, 115, 60)), _helmet((315, 165, 340, 190))),
        (_person(), _person(200)),
    )
    engine.observe(ppe, pose)
    result = engine.observe(ppe, pose)
    assert [person.placement.name for person in result.people] == ["NA_CABECA", "NA_MAO"]
    assert len({person.person_id for person in result.people}) == 2
    assert result.overall.name == "NA_MAO"


def test_one_helmet_on_person_a_does_not_make_person_b_compliant() -> None:
    module = import_module("app.engine.helmet_placement")
    engine = module.HelmetPlacementEngine(stability_frames=1)
    ppe, pose = _batch(7, (_helmet((85, 25, 115, 60)),), (_person(), _person(200)))
    result = engine.observe(ppe, pose)
    assert [person.placement.name for person in result.people] == ["NA_CABECA", "INDETERMINADO"]
    assert result.overall.name == "INDETERMINADO"


def test_worn_helmet_takes_priority_over_another_helmet_in_hand() -> None:
    module = import_module("app.engine.helmet_placement")
    engine = module.HelmetPlacementEngine(stability_frames=1)
    ppe, pose = _batch(
        7,
        (_helmet((85, 25, 115, 60)), _helmet((60, 165, 85, 190))),
        (_person(),),
    )
    assert engine.observe(ppe, pose).overall.name == "NA_CABECA"


def test_temporal_state_and_camera_identity_are_isolated() -> None:
    module = import_module("app.engine.helmet_placement")
    engine = module.HelmetPlacementEngine(stability_frames=3)
    head_1, pose_1 = _batch(1, (_helmet((85, 25, 115, 60)),), (_person(),))
    hand_2, pose_2 = _batch(2, (_helmet((60, 165, 85, 190)),), (_person(),))
    assert engine.observe(head_1, pose_1).overall.name == "INDETERMINADO"
    assert engine.observe(hand_2, pose_2).overall.name == "INDETERMINADO"
    engine.observe(head_1, pose_1)
    assert engine.observe(head_1, pose_1).overall.name == "NA_CABECA"
    assert engine.observe(hand_2, pose_2).overall.name == "INDETERMINADO"
    assert engine.observe(hand_2, pose_2).overall.name == "NA_MAO"
    engine.reset(1)
    assert engine.observe(head_1, pose_1).overall.name == "INDETERMINADO"
    assert engine.observe(hand_2, pose_2).overall.name == "NA_MAO"


def test_missing_pose_never_counts_helmet_detection_as_worn() -> None:
    module = import_module("app.engine.helmet_placement")
    engine = module.HelmetPlacementEngine(stability_frames=1)
    ppe, _pose = _batch(1, (_helmet((85, 25, 115, 60)),), (_person(),))
    assert engine.observe(ppe, None).overall.name == "INDETERMINADO"


def test_pose_from_another_camera_is_not_reused() -> None:
    module = import_module("app.engine.helmet_placement")
    engine = module.HelmetPlacementEngine(stability_frames=1)
    ppe, _ = _batch(1, (_helmet((85, 25, 115, 60)),), (_person(),))
    _, pose = _batch(2, (), (_person(),))
    assert engine.observe(ppe, pose).overall.name == "INDETERMINADO"


@pytest.mark.parametrize(
    ("placement", "status"),
    [
        ("NA_CABECA", PpeSafetyStatus.COMPLIANT),
        ("NA_MAO", PpeSafetyStatus.BLOCKED),
        ("INDETERMINADO", PpeSafetyStatus.PENDING),
    ],
)
def test_helmet_placement_controls_safety_gate(placement, status) -> None:
    module = import_module("app.engine.helmet_placement")
    operation = Operation(41, "Fresa", required_ppe=(PpeRequirement(1, "Capacete", "capacete"),))
    stability = PpeStabilityEngine(
        window_size=3, minimum_samples=1, present_ratio=1, absent_ratio=0
    )
    stability.reset(("capacete",))
    snapshot = stability.observe(("capacete",))
    assessment = PpeSafetyEngine().evaluate(
        operation,
        ("capacete",),
        snapshot,
        helmet_placement=module.HelmetPlacement[placement],
    )
    assert assessment.status is status


def test_windowed_placement_tolerates_unknown_frames_but_not_a_hand() -> None:
    module = import_module("app.engine.helmet_placement")
    engine = module.HelmetPlacementEngine(
        stability_frames=5, window_frames=8, present_ratio=0.75, maximum_missed_frames=3
    )
    head, pose = _batch(1, (_helmet((85, 25, 115, 60)),), (_person(),))
    empty, _ = _batch(1, (), (_person(),))
    hand, _ = _batch(1, (_helmet((60, 165, 85, 190)),), (_person(),))
    no_landmarks = _batch(1, (), (_person(incomplete=True),))[1]
    # Four on the head, one frame without a box, one landmark dropout: history is kept.
    for batch in (head, head, head, head, empty):
        assert engine.observe(batch, pose).overall.name == "INDETERMINADO"
    assert engine.observe(empty, no_landmarks).overall.name == "INDETERMINADO"
    assert engine.observe(head, pose).overall.name == "INDETERMINADO"  # 5/7 < 75%
    assert engine.observe(head, pose).overall.name == "NA_CABECA"  # 6/8
    # Half of the frames without evidence is inconclusive, never confirmed.
    for batch in (empty, head) * 4:
        result = engine.observe(batch, pose).overall.name
    assert result == "INDETERMINADO"
    for _ in range(6):
        result = engine.observe(hand, pose).overall.name
    assert result == "NA_MAO"


def test_indeterminate_helmet_reports_why() -> None:
    module = import_module("app.engine.helmet_placement")
    reason = module.HelmetPendingReason
    engine = module.HelmetPlacementEngine(stability_frames=2)
    head, pose = _batch(1, (_helmet((85, 25, 115, 60)),), (_person(),))
    empty, _ = _batch(1, (), (_person(),))
    far, _ = _batch(1, (_helmet((300, 300, 330, 330)),), (_person(),))
    no_landmarks = _batch(1, (), (_person(incomplete=True),))[1]
    two_people = _batch(1, (), (_person(), _person(offset=200)))[1]
    assert engine.observe(head, None).pending_reason is reason.SEM_POSE
    assert engine.observe(head, no_landmarks).pending_reason is reason.SEM_REFERENCIA
    assert engine.observe(empty, pose).pending_reason is reason.SEM_CAPACETE
    assert engine.observe(far, pose).pending_reason is reason.FORA_DA_CABECA
    assert engine.observe(head, pose).pending_reason is reason.ESTABILIZANDO
    assert engine.observe(head, pose).pending_reason is None
    engine.observe(head, two_people)
    assert engine.observe(head, two_people).pending_reason is reason.OUTRA_PESSOA
