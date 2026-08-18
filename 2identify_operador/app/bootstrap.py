"""Application composition root and lifecycle management."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import cast

from app.core.config import AppSettings, get_settings
from app.core.constants import APPLICATION_NAME, ORGANIZATION_NAME
from app.core.logging_config import configure_logging
from app.core.session import OperatorSessionContext
from app.services.work_session_service import WorkSessionService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Dependencies created once and shared by the application shell."""

    settings: AppSettings
    operator_session: OperatorSessionContext
    work_sessions: WorkSessionService


def create_runtime() -> RuntimeContext:
    """Load configuration and initialize process-wide infrastructure."""

    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "operator_bootstrap_complete",
        extra={"app_environment": settings.app_environment.value},
    )
    return RuntimeContext(
        settings=settings,
        operator_session=OperatorSessionContext(),
        work_sessions=WorkSessionService(
            maximum_authorization_age_seconds=(
                settings.ppe_release_assessment_max_age_seconds
            )
        ),
    )


def run_startup_check(runtime: RuntimeContext) -> int:
    """Perform a headless smoke check useful during installation and support."""

    detector_available = runtime.settings.face_detector_model_path.is_file()
    recognizer_available = runtime.settings.face_recognition_model_path.is_file()
    ppe_model_available = runtime.settings.ppe_model_path.is_file()
    logger.info(
        "operator_startup_check_ok",
        extra={
            "api_url": runtime.settings.api_base_url,
            "log_directory": str(runtime.settings.log_directory),
            "model_path": str(runtime.settings.ppe_model_path),
            "ppe_model_available": ppe_model_available,
            "face_detector_available": detector_available,
            "face_recognizer_available": recognizer_available,
            "face_templates_available": runtime.settings.face_auth_template_store_path.is_file(),
            "operations_mock_enabled": runtime.settings.operations_mock_enabled,
            "manuals_directory_available": runtime.settings.manuals_directory.is_dir(),
        },
    )
    if runtime.settings.face_auth_enabled and not (
        detector_available and recognizer_available
    ):
        logger.error("face_auth_model_artifacts_missing")
        return 1
    return 0


def run_desktop(runtime: RuntimeContext, argv: Sequence[str]) -> int:
    """Create Qt only after the non-UI infrastructure has initialized."""

    from PySide6.QtWidgets import QApplication

    from app.api.client import OperatorApiClient
    from app.controllers.application_controller import ApplicationController
    from app.controllers.credential_login_controller import CredentialLoginController
    from app.controllers.face_login_controller import FaceLoginController
    from app.providers import DesktopManualLauncher, MockOperationProvider
    from app.services.auth_service import AuthService
    from app.services.manual_service import ManualService
    from app.services.operation_service import OperationService
    from app.ui.login import LoginWindow
    from app.ui.styles import load_application_stylesheet

    existing_application = QApplication.instance()
    application = (
        cast(QApplication, existing_application)
        if existing_application is not None
        else QApplication(list(argv))
    )

    application.setApplicationName(APPLICATION_NAME)
    application.setOrganizationName(ORGANIZATION_NAME)
    application.setApplicationVersion(runtime.settings.app_version)
    application.setStyleSheet(load_application_stylesheet())

    _install_exception_hook()

    window = LoginWindow(settings=runtime.settings)
    face_login_controller = FaceLoginController(runtime.settings, window)
    api_client = OperatorApiClient(
        base_url=runtime.settings.api_base_url,
        connect_timeout_seconds=runtime.settings.api_connect_timeout_seconds,
        read_timeout_seconds=runtime.settings.api_read_timeout_seconds,
    )
    credential_login_controller = CredentialLoginController(AuthService(api_client), window)
    manual_service = ManualService(
        manuals_directory=runtime.settings.manuals_directory,
        launcher=DesktopManualLauncher(),
    )
    operation_service: OperationService | None = None
    operations_source_notice: str | None = None
    if runtime.settings.operations_mock_enabled:
        operation_service = OperationService(MockOperationProvider())
        operations_source_notice = "DADOS LOCAIS DE DESENVOLVIMENTO"
        logger.warning("mock_operation_provider_enabled")
    application_controller = ApplicationController(
        session_context=runtime.operator_session,
        login_window=window,
        app_version=runtime.settings.app_version,
        operation_service=operation_service,
        operations_source_notice=operations_source_notice,
        manual_service=manual_service,
        settings=runtime.settings,
        work_session_service=runtime.work_sessions,
    )

    face_login_controller.operator_authenticated.connect(
        application_controller.handle_face_authentication
    )
    credential_login_controller.operator_authenticated.connect(
        application_controller.handle_credential_authentication
    )
    application.aboutToQuit.connect(face_login_controller.shutdown)
    application.aboutToQuit.connect(credential_login_controller.shutdown)
    application.aboutToQuit.connect(application_controller.shutdown)
    application.aboutToQuit.connect(api_client.close)
    application.aboutToQuit.connect(runtime.operator_session.close)
    window.show()

    logger.info("operator_ui_started")
    exit_code = application.exec()
    logger.info("operator_ui_stopped", extra={"exit_code": exit_code})
    return int(exit_code)


def _install_exception_hook() -> None:
    """Log uncaught UI callback exceptions instead of silently losing them."""

    def log_uncaught_exception(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        logger.critical(
            "operator_uncaught_exception",
            exc_info=(exception_type, exception, traceback),
        )

    sys.excepthook = log_uncaught_exception
