from collections.abc import Sequence

import numpy as np

from app.vision.face_auth.pipeline import FaceAuthenticationPipeline
from app.vision.face_auth.types import (
    BoundingBox,
    DetectedFace,
    FaceMatch,
    FacePipelineStatus,
    LivenessDecision,
    LivenessStatus,
    RegisteredFaceTemplate,
)


def _face(size: float = 180) -> DetectedFace:
    return DetectedFace(
        bounding_box=BoundingBox(120, 90, size, size),
        landmarks=((150, 140), (230, 140), (190, 180), (165, 220), (215, 220)),
        confidence=0.99,
        raw_values=tuple(float(index) for index in range(15)),
    )


class DetectorStub:
    def __init__(self, faces: Sequence[DetectedFace]) -> None:
        self.faces = faces

    def detect(self, frame):
        del frame
        return self.faces


class EncoderStub:
    def encode(self, frame, face):
        del frame, face
        return np.ones(128, dtype=np.float32)


class LivenessStub:
    def __init__(self, status: LivenessStatus = LivenessStatus.VERIFIED) -> None:
        self.status = status
        self.reset_count = 0

    def observe(self, face, timestamp):
        del face, timestamp
        return LivenessDecision(self.status, "liveness")

    def reset(self) -> None:
        self.reset_count += 1


class MatcherStub:
    def __init__(self, match: FaceMatch | None) -> None:
        self.match_result = match

    def match(self, embedding):
        del embedding
        return self.match_result


def _match() -> FaceMatch:
    template = RegisteredFaceTemplate(
        operator_id=15,
        name="João Silva",
        model_id="test-model",
        embedding=tuple(1.0 for _ in range(128)),
        profile_photo_reference="var/face_auth/profiles/operator_15.jpg",
    )
    return FaceMatch(template=template, similarity=0.94)


def _pipeline(
    faces: Sequence[DetectedFace],
    liveness_status: LivenessStatus = LivenessStatus.VERIFIED,
    match: FaceMatch | None = None,
    consecutive: int = 2,
) -> FaceAuthenticationPipeline:
    return FaceAuthenticationPipeline(
        detector=DetectorStub(faces),
        encoder=EncoderStub(),
        liveness=LivenessStub(liveness_status),
        matcher=MatcherStub(match),
        minimum_face_ratio=0.18,
        minimum_consecutive_matches=consecutive,
    )


def test_pipeline_rejects_multiple_faces() -> None:
    pipeline = _pipeline([_face(), _face()])
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    decision = pipeline.process(frame, 1.0)

    assert decision.status is FacePipelineStatus.MULTIPLE_FACES


def test_pipeline_waits_for_liveness() -> None:
    pipeline = _pipeline([_face()], LivenessStatus.PENDING)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    decision = pipeline.process(frame, 1.0)

    assert decision.status is FacePipelineStatus.VERIFYING_LIVENESS


def test_pipeline_requires_stable_consecutive_identity() -> None:
    pipeline = _pipeline([_face()], match=_match(), consecutive=2)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    first = pipeline.process(frame, 1.0)
    second = pipeline.process(frame, 1.2)

    assert first.status is FacePipelineStatus.MATCHING
    assert second.status is FacePipelineStatus.RECOGNIZED
    assert second.identity is not None
    assert second.identity.operator_id == 15
    assert second.identity.confidence == 0.94


def test_pipeline_rejects_unknown_face() -> None:
    pipeline = _pipeline([_face()], match=None)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    decision = pipeline.process(frame, 1.0)

    assert decision.status is FacePipelineStatus.NOT_RECOGNIZED

