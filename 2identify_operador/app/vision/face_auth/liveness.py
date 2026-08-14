"""Temporal liveness baseline with explicit fail-closed behavior."""

from __future__ import annotations

from app.vision.face_auth.types import (
    DetectedFace,
    LivenessDecision,
    LivenessStatus,
)


class MotionChallengeLivenessVerifier:
    """Require observable normalized head movement across a minimum duration.

    This is a development baseline, not certified anti-spoofing. It deliberately
    fails closed until movement is observed. A production deployment should replace
    this adapter with a validated passive/depth/IR liveness implementation.
    """

    def __init__(self, minimum_duration_seconds: float, minimum_movement_ratio: float) -> None:
        self._minimum_duration_seconds = minimum_duration_seconds
        self._minimum_movement_ratio = minimum_movement_ratio
        self._started_at: float | None = None
        self._positions: list[tuple[float, float]] = []
        self._verified = False
        self.reset()

    def observe(self, face: DetectedFace, timestamp: float) -> LivenessDecision:
        box = face.bounding_box
        if box.width <= 0 or box.height <= 0:
            self.reset()
            return LivenessDecision(LivenessStatus.REJECTED, "Posição facial inválida.")

        nose_x, nose_y = face.landmarks[2]
        normalized_position = (
            (nose_x - box.x) / box.width,
            (nose_y - box.y) / box.height,
        )
        if self._started_at is None:
            self._started_at = timestamp
        self._positions.append(normalized_position)

        elapsed = timestamp - self._started_at
        x_values = [position[0] for position in self._positions]
        y_values = [position[1] for position in self._positions]
        movement = max(max(x_values) - min(x_values), max(y_values) - min(y_values))

        if elapsed < self._minimum_duration_seconds:
            return LivenessDecision(
                LivenessStatus.PENDING,
                "Mantenha o rosto enquadrado e mova levemente a cabeça.",
            )
        if movement < self._minimum_movement_ratio:
            return LivenessDecision(
                LivenessStatus.PENDING,
                "Mova levemente a cabeça para confirmar sua presença.",
            )

        self._verified = True
        return LivenessDecision(LivenessStatus.VERIFIED, "Prova de vida confirmada.")

    def reset(self) -> None:
        self._started_at = None
        self._positions = []
        self._verified = False


class DevelopmentLivenessBypass:
    """Explicit non-production bypass used only when configuration permits it."""

    def observe(self, face: DetectedFace, timestamp: float) -> LivenessDecision:
        del face, timestamp
        return LivenessDecision(
            LivenessStatus.VERIFIED,
            "Prova de vida desabilitada no ambiente de desenvolvimento.",
        )

    def reset(self) -> None:
        return None
