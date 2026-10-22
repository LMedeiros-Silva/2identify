from collections.abc import Sequence

import numpy as np
import pytest

from app.domain import CredentialAuthenticationResult
from app.vision.face_auth.errors import (
    FaceAuthenticationUnavailableError,
    FaceNotRecognizedError,
)
from app.vision.face_auth.pipeline import FaceAuthenticationPipeline
from app.vision.face_auth.types import (
    BoundingBox,
    DetectedFace,
    FacePipelineStatus,
    LivenessDecision,
    LivenessStatus,
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
    """Each frame gives a slightly different embedding, as a real camera does."""

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, frame, face):
        del frame, face
        self.calls += 1
        vector = np.ones(128, dtype=np.float32)
        vector[0] += self.calls * 0.01
        return vector / np.linalg.norm(vector)


class LivenessStub:
    def __init__(self, status: LivenessStatus = LivenessStatus.VERIFIED) -> None:
        self.status = status
        self.reset_count = 0

    def observe(self, face, timestamp):
        del face, timestamp
        return LivenessDecision(self.status, "liveness")

    def reset(self) -> None:
        self.reset_count += 1


class AuthorityStub:
    """The API: decides who the probes belong to, or rejects."""

    def __init__(self, result: CredentialAuthenticationResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, tuple[np.ndarray, ...]]] = []

    def authenticate(self, model_id, probes):
        self.calls.append((model_id, tuple(probes)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _session() -> CredentialAuthenticationResult:
    return CredentialAuthenticationResult(
        operator_id=21, name="Ana Souza", access_token="employee-session-token"
    )


def _pipeline(
    faces: Sequence[DetectedFace],
    liveness_status: LivenessStatus = LivenessStatus.VERIFIED,
    authority: AuthorityStub | None = None,
    consecutive: int = 2,
    detector: DetectorStub | None = None,
) -> FaceAuthenticationPipeline:
    return FaceAuthenticationPipeline(
        detector=detector or DetectorStub(faces),
        encoder=EncoderStub(),
        liveness=LivenessStub(liveness_status),
        authority=authority or AuthorityStub(_session()),
        model_id="opencv_sface_2021dec",
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


def test_pipeline_sends_consecutive_live_frames_to_the_api_and_returns_its_session() -> None:
    authority = AuthorityStub(_session())
    pipeline = _pipeline([_face()], authority=authority, consecutive=3)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    decisions = [pipeline.process(frame, 1.0 + index * 0.1) for index in range(3)]

    assert [item.status for item in decisions] == [
        FacePipelineStatus.MATCHING,
        FacePipelineStatus.MATCHING,
        FacePipelineStatus.RECOGNIZED,
    ]
    assert len(authority.calls) == 1
    model_id, probes = authority.calls[0]
    assert model_id == "opencv_sface_2021dec" and len(probes) == 3
    assert decisions[-1].identity is not None
    assert decisions[-1].identity.access_token == "employee-session-token"


def test_pipeline_never_sends_probes_from_an_interrupted_sequence() -> None:
    detector = DetectorStub([_face()])
    authority = AuthorityStub(_session())
    pipeline = _pipeline([], authority=authority, consecutive=2, detector=detector)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    pipeline.process(frame, 1.0)
    detector.faces = [_face(), _face()]  # a second person walks in
    assert pipeline.process(frame, 1.1).status is FacePipelineStatus.MULTIPLE_FACES
    detector.faces = [_face()]
    assert pipeline.process(frame, 1.2).status is FacePipelineStatus.MATCHING
    assert authority.calls == []


def test_pipeline_rejects_a_face_the_api_does_not_recognize_and_starts_over() -> None:
    authority = AuthorityStub(FaceNotRecognizedError("x"))
    pipeline = _pipeline([_face()], authority=authority, consecutive=2)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    pipeline.process(frame, 1.0)
    decision = pipeline.process(frame, 1.1)

    assert decision.status is FacePipelineStatus.NOT_RECOGNIZED
    assert decision.identity is None
    assert pipeline.process(frame, 1.2).status is FacePipelineStatus.MATCHING


def test_pipeline_fails_closed_when_the_api_is_unavailable() -> None:
    authority = AuthorityStub(FaceAuthenticationUnavailableError("API fora do ar"))
    pipeline = _pipeline([_face()], authority=authority, consecutive=2)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    pipeline.process(frame, 1.0)
    with pytest.raises(FaceAuthenticationUnavailableError):
        pipeline.process(frame, 1.1)
