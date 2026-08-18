"""Framework-neutral types used throughout facial authentication."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from app.domain.auth import OperatorIdentity
from app.vision.types import Frame as Frame

Embedding = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


@dataclass(frozen=True, slots=True)
class DetectedFace:
    bounding_box: BoundingBox
    landmarks: tuple[tuple[float, float], ...]
    confidence: float
    raw_values: tuple[float, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.landmarks) != 5:
            raise ValueError("a detecção facial deve conter cinco landmarks")
        if len(self.raw_values) < 15:
            raise ValueError("a detecção facial deve conter os 15 valores do YuNet")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence deve estar entre 0.0 e 1.0")


@dataclass(frozen=True, slots=True)
class RegisteredFaceTemplate:
    operator_id: int
    name: str
    model_id: str
    embedding: tuple[float, ...] = field(repr=False)
    profile_photo_reference: str | None = None


class LivenessStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class LivenessDecision:
    status: LivenessStatus
    message: str


@dataclass(frozen=True, slots=True)
class FaceMatch:
    template: RegisteredFaceTemplate
    similarity: float


class FacePipelineStatus(StrEnum):
    WAITING_FACE = "waiting_face"
    MULTIPLE_FACES = "multiple_faces"
    MOVE_CLOSER = "move_closer"
    VERIFYING_LIVENESS = "verifying_liveness"
    MATCHING = "matching"
    NOT_RECOGNIZED = "not_recognized"
    RECOGNIZED = "recognized"


@dataclass(frozen=True, slots=True)
class FacePipelineDecision:
    status: FacePipelineStatus
    message: str
    identity: OperatorIdentity | None = None
