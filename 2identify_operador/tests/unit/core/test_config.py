import pytest
from pydantic import ValidationError

from app.core.config import AppEnvironment, AppSettings
from app.core.constants import PROJECT_ROOT


def test_settings_resolve_relative_paths_from_project_root() -> None:
    settings = AppSettings(
        _env_file=None,
        ppe_model_path="models/custom.pt",
        ultralytics_config_directory="runtime/ultralytics",
        manuals_directory="assets/manuals-test",
        log_directory="runtime/logs",
    )

    assert settings.ppe_model_path == (PROJECT_ROOT / "models/custom.pt").resolve()
    assert settings.ultralytics_config_directory == (
        PROJECT_ROOT / "runtime/ultralytics"
    ).resolve()
    assert settings.manuals_directory == (PROJECT_ROOT / "assets/manuals-test").resolve()
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
    settings = AppSettings(
        _env_file=None,
        app_environment="production",
        operations_mock_enabled=False,
    )

    assert settings.app_environment is AppEnvironment.PRODUCTION


def test_login_camera_has_independent_source() -> None:
    settings = AppSettings(
        _env_file=None,
        camera_source="rtsp://monitoring-camera/live",
        login_camera_source="1",
    )

    assert settings.parsed_camera_source == "rtsp://monitoring-camera/live"
    assert settings.parsed_login_camera_source == 1


def test_operational_camera_runtime_settings_are_validated() -> None:
    settings = AppSettings(
        _env_file=None,
        camera_width=1920,
        camera_height=1080,
        camera_preview_fps=24,
        camera_max_failed_reads=12,
    )

    assert settings.camera_width == 1920
    assert settings.camera_height == 1080
    assert settings.camera_preview_fps == 24
    assert settings.camera_max_failed_reads == 12

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, camera_preview_fps=0)


def test_ppe_inference_runtime_settings_are_typed() -> None:
    settings = AppSettings(
        _env_file=None,
        ppe_confidence_threshold=0.65,
        ppe_iou_threshold=0.40,
        ppe_inference_image_size=960,
        ppe_inference_fps=6,
        ppe_inference_device=" cpu ",
        ppe_stability_window_frames=10,
        ppe_stability_minimum_frames=6,
        ppe_stability_present_ratio=0.80,
        ppe_stability_absent_ratio=0.20,
        ppe_release_assessment_max_age_seconds=1.5,
        ppe_tracking_iou_threshold=0.35,
        ppe_tracking_maximum_missed_batches=4,
        ppe_tracking_minimum_confirmation_hits=3,
        alert_minimum_consecutive_observations=4,
        alert_minimum_persistence_seconds=1.25,
        alert_resolution_consecutive_observations=2,
        alert_cooldown_seconds=45,
    )

    assert settings.ppe_confidence_threshold == 0.65
    assert settings.ppe_iou_threshold == 0.40
    assert settings.ppe_inference_image_size == 960
    assert settings.ppe_inference_fps == 6
    assert settings.ppe_inference_device == "cpu"
    assert settings.ppe_stability_window_frames == 10
    assert settings.ppe_stability_minimum_frames == 6
    assert settings.ppe_stability_present_ratio == 0.80
    assert settings.ppe_stability_absent_ratio == 0.20
    assert settings.ppe_release_assessment_max_age_seconds == 1.5
    assert settings.ppe_tracking_iou_threshold == 0.35
    assert settings.ppe_tracking_maximum_missed_batches == 4
    assert settings.ppe_tracking_minimum_confirmation_hits == 3
    assert settings.alert_minimum_consecutive_observations == 4
    assert settings.alert_minimum_persistence_seconds == 1.25
    assert settings.alert_resolution_consecutive_observations == 2
    assert settings.alert_cooldown_seconds == 45
    assert len(settings.ppe_model_sha256) == 64
    assert settings.ppe_model_sha256 == settings.ppe_model_sha256.casefold()

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, ppe_confidence_threshold=1.1)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, ppe_model_sha256="checksum-inválido")
    with pytest.raises(ValidationError, match="não pode exceder"):
        AppSettings(
            _env_file=None,
            ppe_stability_window_frames=4,
            ppe_stability_minimum_frames=5,
        )
    with pytest.raises(ValidationError, match="deve ser menor"):
        AppSettings(
            _env_file=None,
            ppe_stability_present_ratio=0.50,
            ppe_stability_absent_ratio=0.50,
        )
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, ppe_release_assessment_max_age_seconds=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, ppe_tracking_iou_threshold=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, ppe_tracking_maximum_missed_batches=-1)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, ppe_tracking_minimum_confirmation_hits=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, alert_minimum_consecutive_observations=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, alert_minimum_persistence_seconds=-0.1)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, alert_resolution_consecutive_observations=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, alert_cooldown_seconds=-1)


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


def test_production_rejects_mock_operations() -> None:
    with pytest.raises(ValidationError, match="operações mockadas"):
        AppSettings(
            _env_file=None,
            app_environment="production",
            operations_mock_enabled=True,
        )
