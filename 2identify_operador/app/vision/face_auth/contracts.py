"""Replaceable contracts for facial detection, encoding, liveness and identification."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.auth import CredentialAuthenticationResult
from app.vision.face_auth.types import DetectedFace, Embedding, Frame, LivenessDecision


class FaceDetector(Protocol):
    def detect(self, frame: Frame) -> Sequence[DetectedFace]: ...


class FaceEncoder(Protocol):
    def encode(self, frame: Frame, face: DetectedFace) -> Embedding: ...


class LivenessVerifier(Protocol):
    def observe(self, face: DetectedFace, timestamp: float) -> LivenessDecision: ...

    def reset(self) -> None: ...


class FaceIdentityAuthority(Protocol):
    """The API: it owns the Admin templates and decides who the probes belong to.

    Raises ``FaceNotRecognizedError`` when no single authorized employee matches and
    ``FaceAuthenticationUnavailableError`` when it cannot give a trustworthy answer.
    """

    def authenticate(
        self,
        model_id: str,
        probes: Sequence[Embedding],
    ) -> CredentialAuthenticationResult: ...
