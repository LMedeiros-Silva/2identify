"""Framework-neutral PPE detection contracts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from app.vision.types import Frame


@dataclass(frozen=True, slots=True)
class DetectionBox:
    """One bounding box in source-frame pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        values = (self.x1, self.y1, self.x2, self.y2)
        if not all(isfinite(value) for value in values):
            raise ValueError("coordenadas da detecção devem ser finitas")
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError("caixa da detecção possui limites invertidos")


@dataclass(frozen=True, slots=True)
class PpeDetection:
    """Raw per-frame observation produced by the PPE model."""

    class_id: int
    class_name: str
    confidence: float
    box: DetectionBox

    def __post_init__(self) -> None:
        normalized_name = self.class_name.strip().casefold()
        if self.class_id < 0:
            raise ValueError("class_id deve ser maior ou igual a zero")
        if not normalized_name:
            raise ValueError("class_name não pode ser vazio")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence deve estar entre 0.0 e 1.0")
        object.__setattr__(self, "class_name", normalized_name)


@dataclass(frozen=True, slots=True)
class PpeDetectionBatch:
    """Immutable observations from one frame, without temporal confirmation."""

    detections: tuple[PpeDetection, ...]
    frame_width: int
    frame_height: int
    inference_milliseconds: float

    def __post_init__(self) -> None:
        if self.frame_width <= 0 or self.frame_height <= 0:
            raise ValueError("dimensões do frame devem ser positivas")
        if not isfinite(self.inference_milliseconds) or self.inference_milliseconds < 0:
            raise ValueError("tempo de inferência deve ser finito e não negativo")
        if any(not isinstance(item, PpeDetection) for item in self.detections):
            raise ValueError("detections deve conter somente PpeDetection")

    @property
    def observed_classes(self) -> frozenset[str]:
        return frozenset(item.class_name for item in self.detections)


class PpeDetector(Protocol):
    """Replaceable model adapter consumed by the inference worker."""

    @property
    def class_names(self) -> tuple[str, ...]: ...

    def detect(self, frame: Frame) -> tuple[PpeDetection, ...]: ...
