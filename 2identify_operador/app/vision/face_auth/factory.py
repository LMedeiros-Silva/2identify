"""Composition helpers for the configured biometric pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.core.config import AppEnvironment, AppSettings
from app.domain.auth import CredentialAuthenticationResult
from app.vision.face_auth.contracts import LivenessVerifier
from app.vision.face_auth.errors import FaceAuthenticationUnavailableError
from app.vision.face_auth.liveness import (
    DevelopmentLivenessBypass,
    MotionChallengeLivenessVerifier,
)
from app.vision.face_auth.opencv_models import SFaceEncoder, YuNetFaceDetector
from app.vision.face_auth.pipeline import FaceAuthenticationPipeline
from app.vision.face_auth.types import Embedding

# The API refuses fewer probes; a lower local setting would only produce rejections.
_MINIMUM_PROBES = 3


class FaceApiClient(Protocol):
    def authenticate_face(
        self,
        model_id: str,
        probes: Sequence[Embedding],
        station_token: str,
    ) -> CredentialAuthenticationResult: ...


class _StationFaceAuthority:
    """Bind the workstation credential to the API call; it never identifies a person."""

    def __init__(self, client: FaceApiClient, station_token: str) -> None:
        self._client = client
        self._station_token = station_token

    def authenticate(
        self,
        model_id: str,
        probes: Sequence[Embedding],
    ) -> CredentialAuthenticationResult:
        return self._client.authenticate_face(model_id, probes, self._station_token)


def build_face_authentication_pipeline(
    settings: AppSettings,
    authority: FaceApiClient | None,
) -> FaceAuthenticationPipeline:
    """Face ID always ends in an API session; there is no local-only authorization."""

    station_token = settings.operator_station_token
    if station_token is None:
        raise FaceAuthenticationUnavailableError(
            "Face ID indisponível: configure OPERATOR_STATION_TOKEN nesta estação."
        )
    if authority is None:
        raise FaceAuthenticationUnavailableError("Face ID indisponível: API não configurada.")

    detector = YuNetFaceDetector(
        settings.face_detector_model_path,
        settings.face_auth_detection_threshold,
    )
    encoder = SFaceEncoder(settings.face_recognition_model_path)

    if settings.face_auth_liveness_required:
        liveness: LivenessVerifier = MotionChallengeLivenessVerifier(
            settings.face_auth_liveness_min_duration_seconds,
            settings.face_auth_liveness_min_movement_ratio,
        )
    elif settings.app_environment in {AppEnvironment.DEVELOPMENT, AppEnvironment.TESTING}:
        liveness = DevelopmentLivenessBypass()
    else:
        raise FaceAuthenticationUnavailableError(
            "A prova de vida deve permanecer habilitada neste ambiente."
        )

    return FaceAuthenticationPipeline(
        detector=detector,
        encoder=encoder,
        liveness=liveness,
        authority=_StationFaceAuthority(authority, station_token.get_secret_value()),
        model_id=settings.face_auth_model_id,
        minimum_face_ratio=settings.face_auth_min_face_ratio,
        minimum_consecutive_matches=max(
            settings.face_auth_min_consecutive_matches, _MINIMUM_PROBES
        ),
    )
