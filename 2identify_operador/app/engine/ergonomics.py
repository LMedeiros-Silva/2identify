"""Configurable 2D ergonomic-risk screening from human pose keypoints."""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, atan2, degrees, hypot

from app.domain import SafetyAlertSeverity, SafetyViolation, SafetyViolationType
from app.vision.pose import CocoKeypoint, PersonPose, PoseDetectionBatch, PoseKeypoint


@dataclass(frozen=True, slots=True)
class ErgonomicAssessment:
    """One frame-level screening result, before temporal alert debounce."""

    violations: tuple[SafetyViolation, ...]
    detected_people: int
    evaluated_people: int
    inference_milliseconds: float

    @property
    def is_compliant(self) -> bool:
        return self.evaluated_people > 0 and not self.violations


class ErgonomicsEngine:
    """Screen prolonged awkward postures visible in a two-dimensional image."""

    def __init__(
        self,
        *,
        keypoint_confidence_threshold: float,
        trunk_warning_degrees: float,
        trunk_critical_degrees: float,
        overhead_reach_enabled: bool,
        knee_flexion_enabled: bool,
        knee_warning_degrees: float,
        knee_critical_degrees: float,
    ) -> None:
        if not 0.0 < keypoint_confidence_threshold <= 1.0:
            raise ValueError("keypoint_confidence_threshold deve estar entre 0 e 1")
        if not 0.0 < trunk_warning_degrees < trunk_critical_degrees <= 90.0:
            raise ValueError("limiares de inclinação do tronco são inválidos")
        if not 0.0 < knee_critical_degrees < knee_warning_degrees < 180.0:
            raise ValueError("limiares de flexão do joelho são inválidos")
        self._keypoint_threshold = keypoint_confidence_threshold
        self._trunk_warning = trunk_warning_degrees
        self._trunk_critical = trunk_critical_degrees
        self._overhead_reach_enabled = overhead_reach_enabled
        self._knee_flexion_enabled = knee_flexion_enabled
        self._knee_warning = knee_warning_degrees
        self._knee_critical = knee_critical_degrees

    def evaluate(self, batch: PoseDetectionBatch) -> ErgonomicAssessment:
        if not isinstance(batch, PoseDetectionBatch):
            raise ValueError("batch deve ser PoseDetectionBatch")
        violations: dict[str, SafetyViolation] = {}
        evaluated_people = 0
        for pose in batch.poses:
            pose_violations, evaluated = self._evaluate_pose(pose)
            evaluated_people += int(evaluated)
            for violation in pose_violations:
                current = violations.get(violation.subject_key)
                if current is None or _severity_rank(violation.severity) > _severity_rank(
                    current.severity
                ):
                    violations[violation.subject_key] = violation
        return ErgonomicAssessment(
            violations=tuple(violations[key] for key in sorted(violations)),
            detected_people=len(batch.poses),
            evaluated_people=evaluated_people,
            inference_milliseconds=batch.inference_milliseconds,
        )

    def _evaluate_pose(
        self,
        pose: PersonPose,
    ) -> tuple[tuple[SafetyViolation, ...], bool]:
        violations: list[SafetyViolation] = []
        shoulders = self._midpoint(
            pose,
            CocoKeypoint.LEFT_SHOULDER,
            CocoKeypoint.RIGHT_SHOULDER,
        )
        hips = self._midpoint(
            pose,
            CocoKeypoint.LEFT_HIP,
            CocoKeypoint.RIGHT_HIP,
        )
        evaluated = shoulders is not None and hips is not None
        if shoulders is not None and hips is not None:
            trunk_angle = _angle_from_vertical(hips, shoulders)
            if trunk_angle >= self._trunk_warning:
                severity = (
                    SafetyAlertSeverity.CRITICAL
                    if trunk_angle >= self._trunk_critical
                    else SafetyAlertSeverity.WARNING
                )
                violations.append(
                    SafetyViolation(
                        violation_type=SafetyViolationType.ERGONOMIC_RISK,
                        subject_key="ergonomics:trunk_inclination",
                        summary=(
                            "Risco ergonômico: tronco inclinado "
                            f"{round(trunk_angle)}° em relação à vertical"
                        ),
                        severity=severity,
                    )
                )

        if self._overhead_reach_enabled:
            overhead_sides: list[str] = []
            for side, shoulder_id, wrist_id in (
                ("esquerdo", CocoKeypoint.LEFT_SHOULDER, CocoKeypoint.LEFT_WRIST),
                ("direito", CocoKeypoint.RIGHT_SHOULDER, CocoKeypoint.RIGHT_WRIST),
            ):
                shoulder = self._visible(pose, shoulder_id)
                wrist = self._visible(pose, wrist_id)
                if shoulder is not None and wrist is not None:
                    evaluated = True
                    if wrist.y < shoulder.y:
                        overhead_sides.append(side)
            if overhead_sides:
                both_arms = len(overhead_sides) == 2
                side_description = (
                    "os dois braços"
                    if both_arms
                    else f"o braço {overhead_sides[0]}"
                )
                violations.append(
                    SafetyViolation(
                        violation_type=SafetyViolationType.ERGONOMIC_RISK,
                        subject_key="ergonomics:overhead_reach",
                        summary=(
                            "Risco ergonômico: "
                            f"{side_description} acima da linha dos ombros"
                        ),
                        severity=(
                            SafetyAlertSeverity.CRITICAL
                            if both_arms
                            else SafetyAlertSeverity.WARNING
                        ),
                    )
                )

        if self._knee_flexion_enabled:
            knee_angles: list[float] = []
            for hip_id, knee_id, ankle_id in (
                (
                    CocoKeypoint.LEFT_HIP,
                    CocoKeypoint.LEFT_KNEE,
                    CocoKeypoint.LEFT_ANKLE,
                ),
                (
                    CocoKeypoint.RIGHT_HIP,
                    CocoKeypoint.RIGHT_KNEE,
                    CocoKeypoint.RIGHT_ANKLE,
                ),
            ):
                hip = self._visible(pose, hip_id)
                knee = self._visible(pose, knee_id)
                ankle = self._visible(pose, ankle_id)
                if hip is not None and knee is not None and ankle is not None:
                    evaluated = True
                    knee_angles.append(_joint_angle(hip, knee, ankle))
            if knee_angles:
                minimum_angle = min(knee_angles)
                if minimum_angle <= self._knee_warning:
                    severity = (
                        SafetyAlertSeverity.CRITICAL
                        if minimum_angle <= self._knee_critical
                        else SafetyAlertSeverity.WARNING
                    )
                    violations.append(
                        SafetyViolation(
                            violation_type=SafetyViolationType.ERGONOMIC_RISK,
                            subject_key="ergonomics:deep_knee_flexion",
                            summary=(
                                "Risco ergonômico: flexão acentuada dos joelhos "
                                f"({round(minimum_angle)}°)"
                            ),
                            severity=severity,
                        )
                    )
        return tuple(violations), evaluated

    def _visible(
        self,
        pose: PersonPose,
        keypoint: CocoKeypoint,
    ) -> PoseKeypoint | None:
        value = pose.keypoint(keypoint)
        return value if value.confidence >= self._keypoint_threshold else None

    def _midpoint(
        self,
        pose: PersonPose,
        first: CocoKeypoint,
        second: CocoKeypoint,
    ) -> PoseKeypoint | None:
        left = self._visible(pose, first)
        right = self._visible(pose, second)
        if left is None or right is None:
            return None
        return PoseKeypoint(
            x=(left.x + right.x) / 2.0,
            y=(left.y + right.y) / 2.0,
            confidence=min(left.confidence, right.confidence),
        )


def _angle_from_vertical(origin: PoseKeypoint, target: PoseKeypoint) -> float:
    delta_x = target.x - origin.x
    delta_y = target.y - origin.y
    return degrees(atan2(abs(delta_x), abs(delta_y)))


def _joint_angle(first: PoseKeypoint, vertex: PoseKeypoint, third: PoseKeypoint) -> float:
    first_vector = (first.x - vertex.x, first.y - vertex.y)
    third_vector = (third.x - vertex.x, third.y - vertex.y)
    first_length = hypot(*first_vector)
    third_length = hypot(*third_vector)
    if first_length == 0.0 or third_length == 0.0:
        return 180.0
    cosine = (
        first_vector[0] * third_vector[0] + first_vector[1] * third_vector[1]
    ) / (first_length * third_length)
    return degrees(acos(max(-1.0, min(1.0, cosine))))


def _severity_rank(value: SafetyAlertSeverity) -> int:
    return 2 if value is SafetyAlertSeverity.CRITICAL else 1
