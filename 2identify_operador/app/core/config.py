"""Typed configuration loaded from environment variables and `.env`."""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__
from app.core.constants import PROJECT_ROOT


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Single source of truth for installation-specific configuration."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    app_environment: AppEnvironment = AppEnvironment.DEVELOPMENT
    api_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    api_connect_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 3.0
    api_read_timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 10.0
    operations_mock_enabled: bool = True

    ppe_model_path: Path = Path("models/ppe/best.pt")
    ppe_model_sha256: str = (
        "73A87F86E68F7C5091857F48B55BB756A70B88D0217CC35C58EED3969C7EBA20"
    )
    ppe_confidence_threshold: Annotated[float, Field(gt=0, le=1)] = 0.50
    ppe_iou_threshold: Annotated[float, Field(gt=0, le=1)] = 0.45
    ppe_inference_image_size: Annotated[int, Field(ge=320, le=1920)] = 640
    ppe_inference_fps: Annotated[float, Field(gt=0, le=30)] = 4.0
    ppe_inference_device: str = "cpu"
    ppe_stability_window_frames: Annotated[int, Field(ge=1, le=120)] = 8
    ppe_stability_minimum_frames: Annotated[int, Field(ge=1, le=120)] = 5
    ppe_stability_present_ratio: Annotated[float, Field(gt=0, le=1)] = 0.75
    ppe_stability_absent_ratio: Annotated[float, Field(ge=0, lt=1)] = 0.25
    ppe_release_assessment_max_age_seconds: Annotated[
        float,
        Field(gt=0, le=10),
    ] = 2.0
    ppe_tracking_iou_threshold: Annotated[float, Field(gt=0, le=1)] = 0.30
    ppe_tracking_maximum_missed_batches: Annotated[int, Field(ge=0, le=120)] = 3
    ppe_tracking_minimum_confirmation_hits: Annotated[
        int,
        Field(ge=1, le=120),
    ] = 2
    alert_minimum_consecutive_observations: Annotated[
        int,
        Field(ge=1, le=120),
    ] = 3
    alert_minimum_persistence_seconds: Annotated[
        float,
        Field(ge=0, le=300),
    ] = 0.75
    alert_resolution_consecutive_observations: Annotated[
        int,
        Field(ge=1, le=120),
    ] = 3
    alert_cooldown_seconds: Annotated[float, Field(ge=0, le=86_400)] = 30.0
    ultralytics_config_directory: Path = Path("var/ultralytics")
    manuals_directory: Path = Path("assets/manuals")
    camera_source: str = "0"
    camera_width: Annotated[int, Field(ge=320, le=7680)] = 1280
    camera_height: Annotated[int, Field(ge=240, le=4320)] = 720
    camera_open_timeout_ms: Annotated[int, Field(ge=500, le=60_000)] = 5_000
    camera_read_timeout_ms: Annotated[int, Field(ge=100, le=60_000)] = 2_000
    camera_max_failed_reads: Annotated[int, Field(ge=1, le=300)] = 30
    camera_preview_fps: Annotated[float, Field(gt=0, le=60)] = 20.0
    login_camera_source: str = "0"
    face_auth_enabled: bool = True
    face_auth_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 15.0
    face_detector_model_path: Path = Path("models/face_detection_yunet_2023mar.onnx")
    face_recognition_model_path: Path = Path("models/face_recognition_sface_2021dec.onnx")
    face_auth_template_store_path: Path = Path("var/face_auth/operators.json")
    face_auth_model_id: str = "opencv_sface_2021dec"
    face_auth_confidence_threshold: Annotated[float, Field(gt=0, le=1)] = 0.50
    face_auth_detection_threshold: Annotated[float, Field(gt=0, le=1)] = 0.90
    face_auth_inference_fps: Annotated[float, Field(gt=0, le=30)] = 8.0
    face_auth_preview_fps: Annotated[float, Field(gt=0, le=60)] = 20.0
    face_auth_min_consecutive_matches: Annotated[int, Field(ge=1, le=20)] = 3
    face_auth_min_face_ratio: Annotated[float, Field(gt=0, le=1)] = 0.18
    face_auth_liveness_required: bool = True
    face_auth_liveness_min_duration_seconds: Annotated[float, Field(gt=0, le=10)] = 0.8
    face_auth_liveness_min_movement_ratio: Annotated[float, Field(gt=0, le=0.5)] = 0.045
    face_auth_allow_local_authorization: bool = False
    login_camera_width: Annotated[int, Field(ge=320, le=7680)] = 1280
    login_camera_height: Annotated[int, Field(ge=240, le=4320)] = 720
    login_camera_open_timeout_ms: Annotated[int, Field(ge=500, le=60_000)] = 5_000
    login_camera_read_timeout_ms: Annotated[int, Field(ge=100, le=60_000)] = 2_000
    login_camera_max_failed_reads: Annotated[int, Field(ge=1, le=300)] = 30

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_directory: Path = Path("logs")
    log_file_max_bytes: Annotated[int, Field(ge=1_048_576)] = 10_485_760
    log_file_backup_count: Annotated[int, Field(ge=1, le=30)] = 10

    @field_validator(
        "ppe_model_path",
        "ultralytics_config_directory",
        "manuals_directory",
        "face_detector_model_path",
        "face_recognition_model_path",
        "face_auth_template_store_path",
        "log_directory",
        mode="after",
    )
    @classmethod
    def resolve_project_path(cls, path: Path) -> Path:
        expanded_path = path.expanduser()
        if expanded_path.is_absolute():
            return expanded_path.resolve()
        return (PROJECT_ROOT / expanded_path).resolve()

    @field_validator("camera_source", "login_camera_source", mode="before")
    @classmethod
    def normalize_camera_source(cls, source: object) -> str:
        normalized = str(source).strip()
        if not normalized:
            raise ValueError("CAMERA_SOURCE não pode ser vazio")
        return normalized

    @field_validator("face_auth_model_id")
    @classmethod
    def normalize_face_model_id(cls, model_id: str) -> str:
        normalized = model_id.strip()
        if not normalized:
            raise ValueError("FACE_AUTH_MODEL_ID não pode ser vazio")
        return normalized

    @field_validator("ppe_inference_device")
    @classmethod
    def normalize_ppe_inference_device(cls, device: str) -> str:
        normalized = device.strip()
        if not normalized:
            raise ValueError("PPE_INFERENCE_DEVICE não pode ser vazio")
        return normalized

    @field_validator("ppe_model_sha256")
    @classmethod
    def normalize_ppe_model_sha256(cls, checksum: str) -> str:
        normalized = checksum.strip().casefold()
        if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
            raise ValueError("PPE_MODEL_SHA256 deve possuir 64 caracteres hexadecimais")
        return normalized

    @model_validator(mode="after")
    def enforce_production_biometric_security(self) -> AppSettings:
        if self.ppe_stability_minimum_frames > self.ppe_stability_window_frames:
            raise ValueError(
                "PPE_STABILITY_MINIMUM_FRAMES não pode exceder "
                "PPE_STABILITY_WINDOW_FRAMES"
            )
        if self.ppe_stability_absent_ratio >= self.ppe_stability_present_ratio:
            raise ValueError(
                "PPE_STABILITY_ABSENT_RATIO deve ser menor que "
                "PPE_STABILITY_PRESENT_RATIO"
            )
        if self.app_environment is AppEnvironment.PRODUCTION:
            if not self.face_auth_liveness_required:
                raise ValueError("prova de vida é obrigatória em produção")
            if self.face_auth_allow_local_authorization:
                raise ValueError("autorização facial local é proibida em produção")
            if self.operations_mock_enabled:
                raise ValueError("operações mockadas são proibidas em produção")
        return self

    @property
    def app_version(self) -> str:
        return __version__

    @property
    def api_base_url(self) -> str:
        return str(self.api_url).rstrip("/")

    @property
    def parsed_camera_source(self) -> int | str:
        """Return numeric device indexes as int and URLs/paths as str."""

        if self.camera_source.lstrip("-").isdigit():
            return int(self.camera_source)
        return self.camera_source

    @property
    def parsed_login_camera_source(self) -> int | str:
        """Return the dedicated authentication camera source in OpenCV format."""

        if self.login_camera_source.lstrip("-").isdigit():
            return int(self.login_camera_source)
        return self.login_camera_source


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Build settings once per process."""

    return AppSettings()


def clear_settings_cache() -> None:
    """Reset cached settings for tests and controlled runtime reconfiguration."""

    get_settings.cache_clear()
