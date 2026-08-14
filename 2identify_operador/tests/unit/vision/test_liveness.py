from app.vision.face_auth.liveness import MotionChallengeLivenessVerifier
from app.vision.face_auth.types import BoundingBox, DetectedFace, LivenessStatus


def _face(nose_x: float) -> DetectedFace:
    return DetectedFace(
        bounding_box=BoundingBox(100, 80, 200, 240),
        landmarks=((150, 140), (250, 140), (nose_x, 190), (165, 250), (235, 250)),
        confidence=0.99,
        raw_values=tuple(float(index) for index in range(15)),
    )


def test_motion_liveness_fails_closed_until_duration_and_movement() -> None:
    verifier = MotionChallengeLivenessVerifier(
        minimum_duration_seconds=0.8,
        minimum_movement_ratio=0.045,
    )

    first = verifier.observe(_face(200), timestamp=10.0)
    still = verifier.observe(_face(202), timestamp=11.0)
    moved = verifier.observe(_face(214), timestamp=11.1)

    assert first.status is LivenessStatus.PENDING
    assert still.status is LivenessStatus.PENDING
    assert moved.status is LivenessStatus.VERIFIED


def test_motion_liveness_reset_discards_previous_challenge() -> None:
    verifier = MotionChallengeLivenessVerifier(0.5, 0.04)
    verifier.observe(_face(190), timestamp=1.0)
    verifier.observe(_face(215), timestamp=1.6)

    verifier.reset()
    result = verifier.observe(_face(215), timestamp=3.0)

    assert result.status is LivenessStatus.PENDING

