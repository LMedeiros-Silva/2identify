"""Composition helpers for the configured local biometric pipeline."""

from __future__ import annotations

from app.core.config import AppEnvironment, AppSettings
from app.vision.face_auth.contracts import LivenessVerifier
from app.vision.face_auth.errors import FaceAuthenticationUnavailableError
from app.vision.face_auth.liveness import (
    DevelopmentLivenessBypass,
    MotionChallengeLivenessVerifier,
)
from app.vision.face_auth.matcher import CosineFaceMatcher
from app.vision.face_auth.opencv_models import SFaceEncoder, YuNetFaceDetector
from app.vision.face_auth.pipeline import FaceAuthenticationPipeline
from app.vision.face_auth.repository import JsonFaceTemplateRepository


def build_local_face_authentication_pipeline(settings: AppSettings) -> FaceAuthenticationPipeline:
    """Build the current local adapter; production will replace authorization with the API."""

    if not settings.face_auth_allow_local_authorization:
        raise FaceAuthenticationUnavailableError(
            "A autorização facial pela API ainda não foi configurada neste equipamento."
        )

    repository = JsonFaceTemplateRepository(settings.face_auth_template_store_path)
    templates = repository.load_templates(settings.face_auth_model_id)
    matcher = CosineFaceMatcher(templates, settings.face_auth_confidence_threshold)
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
        matcher=matcher,
        minimum_face_ratio=settings.face_auth_min_face_ratio,
        minimum_consecutive_matches=settings.face_auth_min_consecutive_matches,
    )
