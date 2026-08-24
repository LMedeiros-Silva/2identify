from __future__ import annotations

from app.domain import SafetyAlertSeverity, SafetyViolationType
from app.engine import ErgonomicsEngine
from app.vision.pose import (
    COCO_KEYPOINT_COUNT,
    CocoKeypoint,
    PersonPose,
    PoseDetectionBatch,
    PoseKeypoint,
)


def _pose(points: dict[CocoKeypoint, tuple[float, float]]) -> PersonPose:
    keypoints = [PoseKeypoint(0.0, 0.0, 0.0) for _ in range(COCO_KEYPOINT_COUNT)]
    for index, (x, y) in points.items():
        keypoints[int(index)] = PoseKeypoint(x, y, 0.95)
    return PersonPose(confidence=0.92, keypoints=tuple(keypoints))


def _engine() -> ErgonomicsEngine:
    return ErgonomicsEngine(
        keypoint_confidence_threshold=0.5,
        trunk_warning_degrees=20,
        trunk_critical_degrees=45,
        overhead_reach_enabled=True,
        knee_flexion_enabled=False,
        knee_warning_degrees=120,
        knee_critical_degrees=90,
    )


def _batch(pose: PersonPose) -> PoseDetectionBatch:
    return PoseDetectionBatch((pose,), 640, 480, 12.5)


def test_upright_operator_is_evaluated_without_violation() -> None:
    pose = _pose(
        {
            CocoKeypoint.LEFT_SHOULDER: (280, 160),
            CocoKeypoint.RIGHT_SHOULDER: (360, 160),
            CocoKeypoint.LEFT_HIP: (290, 320),
            CocoKeypoint.RIGHT_HIP: (350, 320),
            CocoKeypoint.LEFT_WRIST: (260, 260),
            CocoKeypoint.RIGHT_WRIST: (380, 260),
        }
    )

    assessment = _engine().evaluate(_batch(pose))

    assert assessment.is_compliant
    assert assessment.evaluated_people == 1
    assert assessment.violations == ()


def test_critical_trunk_inclination_and_both_overhead_arms_are_reported() -> None:
    pose = _pose(
        {
            CocoKeypoint.LEFT_SHOULDER: (540, 130),
            CocoKeypoint.RIGHT_SHOULDER: (620, 130),
            CocoKeypoint.LEFT_HIP: (270, 320),
            CocoKeypoint.RIGHT_HIP: (330, 320),
            CocoKeypoint.LEFT_WRIST: (550, 70),
            CocoKeypoint.RIGHT_WRIST: (610, 70),
        }
    )

    assessment = _engine().evaluate(_batch(pose))

    assert {item.subject_key for item in assessment.violations} == {
        "ergonomics:overhead_reach",
        "ergonomics:trunk_inclination",
    }
    assert all(
        item.violation_type is SafetyViolationType.ERGONOMIC_RISK
        for item in assessment.violations
    )
    assert all(
        item.severity is SafetyAlertSeverity.CRITICAL
        for item in assessment.violations
    )


def test_low_confidence_keypoints_are_not_used_for_posture_decisions() -> None:
    assessment = _engine().evaluate(
        _batch(
            PersonPose(
                confidence=0.8,
                keypoints=tuple(
                    PoseKeypoint(float(index), float(index), 0.2)
                    for index in range(COCO_KEYPOINT_COUNT)
                ),
            )
        )
    )

    assert assessment.evaluated_people == 0
    assert not assessment.is_compliant
    assert assessment.violations == ()
