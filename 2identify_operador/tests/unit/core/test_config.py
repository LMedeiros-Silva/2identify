import pytest
from pydantic import ValidationError

from app.core.config import AppEnvironment, AppSettings
from app.core.constants import PROJECT_ROOT


def test_settings_resolve_relative_paths_from_project_root() -> None:
    settings = AppSettings(
        _env_file=None,
        ppe_model_path="models/custom.pt",
        log_directory="runtime/logs",
    )

    assert settings.ppe_model_path == (PROJECT_ROOT / "models/custom.pt").resolve()
    assert settings.log_directory == (PROJECT_ROOT / "runtime/logs").resolve()


@pytest.mark.parametrize(
    ("configured_source", "expected_source"),
    [("0", 0), ("-1", -1), ("rtsp://camera.local/live", "rtsp://camera.local/live")],
)
def test_camera_source_is_parsed_without_losing_url_support(
    configured_source: str,
    expected_source: int | str,
) -> None:
    settings = AppSettings(_env_file=None, camera_source=configured_source)

    assert settings.parsed_camera_source == expected_source


def test_invalid_timeout_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, api_connect_timeout_seconds=0)


def test_environment_is_typed() -> None:
    settings = AppSettings(_env_file=None, app_environment="production")

    assert settings.app_environment is AppEnvironment.PRODUCTION


def test_login_camera_has_independent_source() -> None:
    settings = AppSettings(
        _env_file=None,
        camera_source="rtsp://monitoring-camera/live",
        login_camera_source="1",
    )

    assert settings.parsed_camera_source == "rtsp://monitoring-camera/live"
    assert settings.parsed_login_camera_source == 1


def test_face_auth_threshold_is_validated() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, face_auth_confidence_threshold=1.01)


def test_production_rejects_local_face_authorization() -> None:
    with pytest.raises(ValidationError, match="autorização facial local"):
        AppSettings(
            _env_file=None,
            app_environment="production",
            face_auth_allow_local_authorization=True,
        )


def test_production_requires_liveness() -> None:
    with pytest.raises(ValidationError, match="prova de vida"):
        AppSettings(
            _env_file=None,
            app_environment="production",
            face_auth_liveness_required=False,
        )
