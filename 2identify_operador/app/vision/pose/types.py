"""Framework-neutral pose-estimation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from math import isfinite
from typing import Protocol

from app.vision.types import Frame


class CocoKeypoint(IntEnum):
    """Indices emitted by Ultralytics COCO human-pose checkpoints."""

    NOSE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    LEFT_EAR = 3
    RIGHT_EAR = 4
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_ELBOW = 7
    RIGHT_ELBOW = 8
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12
    LEFT_KNEE = 13
    RIGHT_KNEE = 14
    LEFT_ANKLE = 15
    RIGHT_ANKLE = 16


COCO_KEYPOINT_COUNT = len(CocoKeypoint)


@dataclass(frozen=True, slots=True)
class PoseKeypoint:
    """One keypoint in source-frame pixel coordinates."""

    x: float
    y: float
    confidence: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x, self.y, self.confidence)):
            raise ValueError("keypoint deve conter apenas valores finitos")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence deve estar entre 0.0 e 1.0")


@dataclass(frozen=True, slots=True)
class PersonPose:
    """One detected person with the standard 17 COCO keypoints."""

    confidence: float
    keypoints: tuple[PoseKeypoint, ...]

    def __post_init__(self) -> None:
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence da pose deve estar entre 0.0 e 1.0")
        if len(self.keypoints) != COCO_KEYPOINT_COUNT:
            raise ValueError("a pose humana deve possuir 17 keypoints COCO")
        if any(not isinstance(item, PoseKeypoint) for item in self.keypoints):
            raise ValueError("keypoints deve conter somente PoseKeypoint")

    def keypoint(self, keypoint: CocoKeypoint) -> PoseKeypoint:
        return self.keypoints[int(keypoint)]


@dataclass(frozen=True, slots=True)
class PoseDetectionBatch:
    """Immutable pose observations produced from one camera frame."""

    poses: tuple[PersonPose, ...]
    frame_width: int
    frame_height: int
    inference_milliseconds: float
    camera_id: int | None = None
    generation: int = 0
    captured_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.camera_id is not None and self.camera_id <= 0:
            raise ValueError("camera_id deve ser positivo")
        if self.frame_width <= 0 or self.frame_height <= 0:
            raise ValueError("dimensões do frame devem ser positivas")
        if not isfinite(self.inference_milliseconds) or self.inference_milliseconds < 0:
            raise ValueError("tempo de inferência deve ser finito e não negativo")
        if any(not isinstance(item, PersonPose) for item in self.poses):
            raise ValueError("poses deve conter somente PersonPose")


class PoseEstimator(Protocol):
    """Replaceable local model adapter consumed by the Qt worker."""

    def estimate(self, frame: Frame) -> tuple[PersonPose, ...]: ...
