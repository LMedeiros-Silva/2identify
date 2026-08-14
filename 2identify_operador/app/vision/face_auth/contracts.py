"""Replaceable contracts for facial detection, encoding, liveness and templates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.vision.face_auth.types import (
    DetectedFace,
    Embedding,
    FaceMatch,
    Frame,
    LivenessDecision,
    RegisteredFaceTemplate,
)


class FaceDetector(Protocol):
    def detect(self, frame: Frame) -> Sequence[DetectedFace]: ...


class FaceEncoder(Protocol):
    def encode(self, frame: Frame, face: DetectedFace) -> Embedding: ...


class LivenessVerifier(Protocol):
    def observe(self, face: DetectedFace, timestamp: float) -> LivenessDecision: ...

    def reset(self) -> None: ...


class FaceTemplateRepository(Protocol):
    def load_templates(self, model_id: str) -> Sequence[RegisteredFaceTemplate]: ...


class FaceMatcher(Protocol):
    def match(self, embedding: Embedding) -> FaceMatch | None: ...

