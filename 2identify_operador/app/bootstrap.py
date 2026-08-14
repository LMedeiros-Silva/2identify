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

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Dependencies created once and shared by the application shell."""

    settings: AppSettings


def create_runtime() -> RuntimeContext:
    """Load configuration and initialize process-wide infrastructure."""

    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "operator_bootstrap_complete",
        extra={"app_environment": settings.app_environment.value},
    )
    return RuntimeContext(settings=settings)


def run_startup_check(runtime: RuntimeContext) -> int:
    """Perform a headless smoke check useful during installation and support."""

    detector_available = runtime.settings.face_detector_model_path.is_file()
    recognizer_available = runtime.settings.face_recognition_model_path.is_file()
    logger.info(
        "operator_startup_check_ok",
        extra={
            "api_url": runtime.settings.api_base_url,
            "log_directory": str(runtime.settings.log_directory),
            "model_path": str(runtime.settings.ppe_model_path),
            "face_detector_available": detector_available,
            "face_recognizer_available": recognizer_available,
            "face_templates_available": runtime.settings.face_auth_template_store_path.is_file(),
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

    from app.controllers.face_login_controller import FaceLoginController
    from app.domain.auth import LoginCredentials, OperatorIdentity
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

    def handle_face_login_success(result: object) -> None:
        if not isinstance(result, OperatorIdentity):
            logger.error("invalid_face_login_result_type")
            return
        logger.info(
            "operator_session_navigation_pending",
            extra={"operator_id": result.operator_id, "target": "main_window_stage_3"},
        )

    def handle_credential_login_request(request: object) -> None:
        if not isinstance(request, LoginCredentials):
            logger.error("invalid_login_request_type")
            window.show_credential_authentication_error(
                "Não foi possível processar a solicitação."
            )
            return

        logger.info(
            "operator_login_requested",
            extra={"username": request.username, "integration_status": "pending"},
        )
        window.show_credential_authentication_notice(
            "A autenticação pela API será conectada na etapa de integração. "
            "A interface de acesso está pronta."
        )

    face_login_controller.operator_authenticated.connect(handle_face_login_success)
    window.credential_login_requested.connect(handle_credential_login_request)
    application.aboutToQuit.connect(face_login_controller.shutdown)
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
