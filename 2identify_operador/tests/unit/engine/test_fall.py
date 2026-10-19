"""Fall screening: geometry plus persistence, never a single frame."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import SafetyAlertSeverity, SafetyViolationType
from app.engine import FallDetectionEngine, FallPosture, FallPostureClassifier
from app.vision.pose import COCO_KEYPOINT_COUNT, CocoKeypoint, PersonPose, PoseKeypoint

_T0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
K = CocoKeypoint


def _pose(points: dict[CocoKeypoint, tuple[float, float]]) -> PersonPose:
    keypoints = [PoseKeypoint(0, 0, 0) for _ in range(COCO_KEYPOINT_COUNT)]
    for key, (x, y) in points.items():
        keypoints[int(key)] = PoseKeypoint(x, y, 0.95)
    return PersonPose(0.95, tuple(keypoints))


STANDING = _pose(
    {
        K.NOSE: (100, 40),
        K.LEFT_SHOULDER: (85, 80),
        K.RIGHT_SHOULDER: (115, 80),
        K.LEFT_HIP: (90, 160),
        K.RIGHT_HIP: (110, 160),
        K.LEFT_KNEE: (90, 220),
        K.RIGHT_KNEE: (110, 220),
        K.LEFT_ANKLE: (90, 280),
        K.RIGHT_ANKLE: (110, 280),
    }
)
LYING = _pose(
    {
        K.NOSE: (40, 300),
        K.LEFT_SHOULDER: (80, 290),
        K.RIGHT_SHOULDER: (80, 310),
        K.LEFT_HIP: (160, 290),
        K.RIGHT_HIP: (160, 310),
        K.LEFT_KNEE: (220, 292),
        K.RIGHT_KNEE: (220, 312),
        K.LEFT_ANKLE: (280, 295),
        K.RIGHT_ANKLE: (280, 315),
    }
)
# Deep squat leaning forward: knees ahead, trunk about 50 degrees from vertical.
SQUAT = _pose(
    {
        K.NOSE: (175, 170),
        K.LEFT_SHOULDER: (155, 190),
        K.RIGHT_SHOULDER: (165, 190),
        K.LEFT_HIP: (95, 240),
        K.RIGHT_HIP: (105, 240),
        K.LEFT_KNEE: (150, 230),
        K.RIGHT_KNEE: (160, 230),
        K.LEFT_ANKLE: (110, 285),
        K.RIGHT_ANKLE: (120, 285),
    }
)
# Bending forward at the waist: trunk horizontal, legs vertical.
BENDING = _pose(
    {
        K.NOSE: (210, 175),
        K.LEFT_SHOULDER: (180, 152),
        K.RIGHT_SHOULDER: (180, 168),
        K.LEFT_HIP: (100, 152),
        K.RIGHT_HIP: (100, 168),
        K.LEFT_KNEE: (98, 220),
        K.RIGHT_KNEE: (102, 220),
        K.LEFT_ANKLE: (98, 290),
        K.RIGHT_ANKLE: (102, 290),
    }
)
# Sitting on a chair: upright trunk, thighs horizontal.
SITTING = _pose(
    {
        K.NOSE: (100, 60),
        K.LEFT_SHOULDER: (88, 100),
        K.RIGHT_SHOULDER: (112, 100),
        K.LEFT_HIP: (92, 180),
        K.RIGHT_HIP: (108, 180),
        K.LEFT_KNEE: (150, 182),
        K.RIGHT_KNEE: (160, 182),
        K.LEFT_ANKLE: (150, 250),
        K.RIGHT_ANKLE: (160, 250),
    }
)
# Lying, but the legs are out of the frame: indistinguishable from bending forward.
LYING_NO_LEGS = _pose(
    {
        K.NOSE: (40, 300),
        K.LEFT_SHOULDER: (80, 290),
        K.RIGHT_SHOULDER: (80, 310),
        K.LEFT_HIP: (160, 290),
        K.RIGHT_HIP: (160, 310),
    }
)


def _classifier() -> FallPostureClassifier:
    return FallPostureClassifier(
        keypoint_confidence_threshold=0.5,
        lying_trunk_degrees=60,
        upright_trunk_degrees=40,
        lying_aspect_ratio=1.2,
    )


def _engine() -> FallDetectionEngine:
    return FallDetectionEngine(
        _classifier(),
        confirmation_seconds=2.0,
        minimum_frames=3,
        recovery_seconds=3.0,
        evidence_gap_seconds=1.5,
    )


def _feed(engine, pose, start: datetime, seconds: float, step: float = 0.25):
    result = None
    elapsed = 0.0
    while elapsed <= seconds + 1e-9:
        poses = (pose,) if pose is not None else ()
        result = engine.observe(poses, start + timedelta(seconds=elapsed))
        elapsed += step
    return result, start + timedelta(seconds=seconds)


@pytest.mark.parametrize(
    ("pose", "expected"),
    [
        (STANDING, FallPosture.UPRIGHT),
        (LYING, FallPosture.LYING),
        (SQUAT, FallPosture.OTHER),
        (BENDING, FallPosture.OTHER),
        (SITTING, FallPosture.UPRIGHT),
        (LYING_NO_LEGS, FallPosture.UNKNOWN),
    ],
)
def test_posture_geometry(pose, expected) -> None:
    assert _classifier().classify(pose).posture is expected


def test_a_single_lying_frame_never_confirms_a_fall() -> None:
    engine = _engine()

    assert engine.observe((LYING,), _T0) is None
    assert engine.observe((STANDING,), _T0 + timedelta(seconds=0.25)) is None
    assert not engine.confirmed


def test_persistent_lying_posture_confirms_a_critical_fall() -> None:
    engine = _engine()

    early, _ = _feed(engine, LYING, _T0, 1.5)
    confirmed, _ = _feed(engine, LYING, _T0 + timedelta(seconds=1.75), 0.5)

    assert early is None
    assert confirmed is not None
    assert confirmed.violation_type is SafetyViolationType.FALL_DETECTED
    assert confirmed.severity is SafetyAlertSeverity.CRITICAL
    assert confirmed.escalate is False


@pytest.mark.parametrize("pose", [SQUAT, BENDING, SITTING, STANDING, LYING_NO_LEGS])
def test_squatting_bending_or_sitting_for_long_is_not_a_fall(pose) -> None:
    engine = _engine()

    result, _ = _feed(engine, pose, _T0, 10.0)

    assert result is None


def test_brief_keypoint_loss_does_not_interrupt_confirmation() -> None:
    engine = _engine()
    _, at = _feed(engine, LYING, _T0, 1.0)
    _, at = _feed(engine, None, at + timedelta(seconds=0.25), 0.75)
    result, _ = _feed(engine, LYING, at + timedelta(seconds=0.25), 0.5)

    assert result is not None


def test_long_keypoint_loss_restarts_the_confirmation() -> None:
    engine = _engine()
    _, at = _feed(engine, LYING, _T0, 1.5)
    _, at = _feed(engine, None, at + timedelta(seconds=0.25), 2.0)
    result, _ = _feed(engine, LYING, at + timedelta(seconds=0.25), 1.0)

    assert result is None


def test_stable_upright_posture_recovers_and_a_brief_one_does_not() -> None:
    engine = _engine()
    _, at = _feed(engine, LYING, _T0, 2.5)
    assert engine.confirmed

    # Getting up for one second and lying down again is not a recovery.
    _, at = _feed(engine, STANDING, at + timedelta(seconds=0.25), 1.0)
    still, at = _feed(engine, LYING, at + timedelta(seconds=0.25), 0.5)
    assert still is not None

    # Keypoints lost while lying keep the fall active (no evidence of recovery).
    lost, at = _feed(engine, None, at + timedelta(seconds=0.25), 5.0)
    assert lost is not None

    recovered, _ = _feed(engine, STANDING, at + timedelta(seconds=0.25), 3.25)
    assert recovered is None
    assert not engine.confirmed


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        FallPostureClassifier(
            keypoint_confidence_threshold=0.5,
            lying_trunk_degrees=40,
            upright_trunk_degrees=60,
            lying_aspect_ratio=1.2,
        )
    with pytest.raises(ValueError):
        FallDetectionEngine(
            _classifier(),
            confirmation_seconds=2,
            minimum_frames=1,
            recovery_seconds=3,
            evidence_gap_seconds=1,
        )
