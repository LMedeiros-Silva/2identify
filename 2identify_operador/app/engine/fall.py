"""Possible-fall screening from 2D pose geometry with temporal confirmation.

A single frame never confirms a fall. A person is considered lying when the trunk
is close to horizontal *and* the visible body is wider than tall. Squatting,
sitting and leaning keep the trunk closer to vertical; bending forward keeps the
legs vertical, so the body stays taller than wide. Recovery requires a stable
upright trunk; frames without usable keypoints are neutral.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import atan2, degrees, hypot

from app.domain import SafetyAlertSeverity, SafetyViolation, SafetyViolationType
from app.vision.pose import CocoKeypoint, PersonPose, PoseKeypoint

_HEAD = (
    CocoKeypoint.NOSE,
    CocoKeypoint.LEFT_EYE,
    CocoKeypoint.RIGHT_EYE,
    CocoKeypoint.LEFT_EAR,
    CocoKeypoint.RIGHT_EAR,
)
_LEGS = (
    CocoKeypoint.LEFT_KNEE,
    CocoKeypoint.RIGHT_KNEE,
    CocoKeypoint.LEFT_ANKLE,
    CocoKeypoint.RIGHT_ANKLE,
)


class FallPosture(StrEnum):
    UPRIGHT = "upright"
    LYING = "lying"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FallPostureReading:
    posture: FallPosture
    trunk_angle: float | None = None
    aspect_ratio: float | None = None


class FallPostureClassifier:
    """Classify one pose as upright, lying, other or not evaluable."""

    def __init__(
        self,
        *,
        keypoint_confidence_threshold: float,
        lying_trunk_degrees: float,
        upright_trunk_degrees: float,
        lying_aspect_ratio: float,
    ) -> None:
        if not 0.0 < keypoint_confidence_threshold <= 1.0:
            raise ValueError("keypoint_confidence_threshold deve estar entre 0 e 1")
        if not 0.0 < upright_trunk_degrees < lying_trunk_degrees <= 90.0:
            raise ValueError("limiares de tronco para queda são inválidos")
        if lying_aspect_ratio <= 0.0:
            raise ValueError("lying_aspect_ratio deve ser positivo")
        self._threshold = keypoint_confidence_threshold
        self._lying_trunk = lying_trunk_degrees
        self._upright_trunk = upright_trunk_degrees
        self._lying_aspect = lying_aspect_ratio

    def classify(self, pose: PersonPose) -> FallPostureReading:
        shoulders = self._midpoint(pose, CocoKeypoint.LEFT_SHOULDER, CocoKeypoint.RIGHT_SHOULDER)
        hips = self._midpoint(pose, CocoKeypoint.LEFT_HIP, CocoKeypoint.RIGHT_HIP)
        if shoulders is None or hips is None:
            return FallPostureReading(FallPosture.UNKNOWN)
        if hypot(shoulders.x - hips.x, shoulders.y - hips.y) <= 1.0:
            return FallPostureReading(FallPosture.UNKNOWN)
        trunk_angle = degrees(atan2(abs(shoulders.x - hips.x), abs(shoulders.y - hips.y)))
        if trunk_angle <= self._upright_trunk:
            return FallPostureReading(FallPosture.UPRIGHT, trunk_angle)
        legs = [point for point in (self._visible(pose, item) for item in _LEGS) if point]
        if not legs:
            # Without the legs, lying and bending forward look the same in 2D.
            return FallPostureReading(FallPosture.UNKNOWN, trunk_angle)
        head = [point for point in (self._visible(pose, item) for item in _HEAD) if point]
        points = [
            point
            for point in (
                self._visible(pose, CocoKeypoint.LEFT_SHOULDER),
                self._visible(pose, CocoKeypoint.RIGHT_SHOULDER),
                self._visible(pose, CocoKeypoint.LEFT_HIP),
                self._visible(pose, CocoKeypoint.RIGHT_HIP),
            )
            if point
        ]
        points.extend(legs)
        points.extend(head)
        width = max(item.x for item in points) - min(item.x for item in points)
        height = max(item.y for item in points) - min(item.y for item in points)
        aspect_ratio = width / max(height, 1.0)
        if trunk_angle >= self._lying_trunk and aspect_ratio >= self._lying_aspect:
            return FallPostureReading(FallPosture.LYING, trunk_angle, aspect_ratio)
        return FallPostureReading(FallPosture.OTHER, trunk_angle, aspect_ratio)

    def _visible(self, pose: PersonPose, keypoint: CocoKeypoint) -> PoseKeypoint | None:
        value = pose.keypoint(keypoint)
        return value if value.confidence >= self._threshold else None

    def _midpoint(
        self, pose: PersonPose, first: CocoKeypoint, second: CocoKeypoint
    ) -> PoseKeypoint | None:
        left = self._visible(pose, first)
        right = self._visible(pose, second)
        if left is None or right is None:
            return None
        return PoseKeypoint(
            (left.x + right.x) / 2.0,
            (left.y + right.y) / 2.0,
            min(left.confidence, right.confidence),
        )


class FallDetectionEngine:
    """Confirm a possible fall only after a persistent lying posture, per camera stream."""

    def __init__(
        self,
        classifier: FallPostureClassifier,
        *,
        confirmation_seconds: float,
        minimum_frames: int,
        recovery_seconds: float,
        evidence_gap_seconds: float,
    ) -> None:
        if confirmation_seconds <= 0 or recovery_seconds <= 0 or evidence_gap_seconds <= 0:
            raise ValueError("tempos da detecção de queda devem ser positivos")
        if minimum_frames < 2:
            raise ValueError("a queda exige pelo menos dois quadros")
        self._classifier = classifier
        self._confirmation = timedelta(seconds=confirmation_seconds)
        self._minimum_frames = minimum_frames
        self._recovery = timedelta(seconds=recovery_seconds)
        self._gap = timedelta(seconds=evidence_gap_seconds)
        self.reset()

    @property
    def confirmed(self) -> bool:
        return self._confirmed

    def reset(self) -> None:
        self._confirmed = False
        self._candidate_since: datetime | None = None
        self._last_lying_at: datetime | None = None
        self._lying_frames = 0
        self._upright_since: datetime | None = None
        self._upright_frames = 0

    def observe(
        self, poses: tuple[PersonPose, ...], observed_at: datetime
    ) -> SafetyViolation | None:
        """Advance with one frame and return the active fall violation, if any."""

        observed_at = _as_utc(observed_at)
        posture = self._frame_posture(poses)
        if not self._confirmed:
            self._advance_candidate(posture, observed_at)
        else:
            self._advance_recovery(posture, observed_at)
        if not self._confirmed:
            return None
        return SafetyViolation(
            violation_type=SafetyViolationType.FALL_DETECTED,
            subject_key="fall:person",
            summary="Possível queda detectada: pessoa deitada no chão",
            severity=SafetyAlertSeverity.CRITICAL,
            escalate=False,
        )

    def _frame_posture(self, poses: tuple[PersonPose, ...]) -> FallPosture:
        postures = {self._classifier.classify(pose).posture for pose in poses}
        for posture in (FallPosture.LYING, FallPosture.UPRIGHT, FallPosture.OTHER):
            if posture in postures:
                return posture
        return FallPosture.UNKNOWN

    def _advance_candidate(self, posture: FallPosture, observed_at: datetime) -> None:
        if posture is FallPosture.LYING:
            if (
                self._candidate_since is None
                or self._last_lying_at is None
                or observed_at - self._last_lying_at > self._gap
            ):
                self._candidate_since = observed_at
                self._lying_frames = 0
            self._lying_frames += 1
            self._last_lying_at = observed_at
            if (
                self._lying_frames >= self._minimum_frames
                and observed_at - self._candidate_since >= self._confirmation
            ):
                self._confirmed = True
                self._upright_since = None
                self._upright_frames = 0
        elif posture is FallPosture.UPRIGHT or (
            self._last_lying_at is not None and observed_at - self._last_lying_at > self._gap
        ):
            self._candidate_since = None
            self._last_lying_at = None
            self._lying_frames = 0

    def _advance_recovery(self, posture: FallPosture, observed_at: datetime) -> None:
        if posture is FallPosture.UPRIGHT:
            if self._upright_since is None:
                self._upright_since = observed_at
                self._upright_frames = 0
            self._upright_frames += 1
            if (
                self._upright_frames >= self._minimum_frames
                and observed_at - self._upright_since >= self._recovery
            ):
                self.reset()
        elif posture is not FallPosture.UNKNOWN:
            # Lying again or only partially up: the recovery has not stabilized.
            self._upright_since = None
            self._upright_frames = 0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at deve possuir fuso horário")
    return value.astimezone(UTC)
