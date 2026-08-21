from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication

from app.api import AdminApiClient
from app.controllers.dashboard_controller import DashboardController
from app.controllers.login_controller import LoginController
from app.controllers.realtime_controller import RealtimeController
from app.core.config import Settings
from app.core.session import AdminSessionContext
from app.domain import AdminAuthentication
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_dashboard_service import AdminDashboardService
from app.ui.login.login_window import LoginWindow
from app.ui.main.main_window import MainWindow

logger = logging.getLogger(__name__)


class ApplicationController(QObject):
    """Controla o ciclo login → dashboard → logout sem persistir o token."""

    def __init__(
        self,
        application: QApplication,
        settings: Settings,
        api_client: AdminApiClient,
        *,
        realtime_controller_factory: Callable[..., RealtimeController] = RealtimeController,
    ) -> None:
        super().__init__()
        self._application = application
        self._settings = settings
        self._api_client = api_client
        self._session_context = AdminSessionContext()
        self._auth_service = AdminAuthService(api_client)
        self._dashboard_service = AdminDashboardService(api_client)
        self._realtime_controller_factory = realtime_controller_factory
        self._shutting_down = False
        self._pending_login_message: str | None = None

        self.login_window = LoginWindow()
        self.login_controller = LoginController(
            self.login_window,
            self._auth_service,
            shutdown_timeout_ms=settings.worker_shutdown_timeout_ms,
        )
        self.login_controller.authenticated.connect(self._open_dashboard)

        self.main_window: MainWindow | None = None
        self.dashboard_controller: DashboardController | None = None
        self.realtime_controller: RealtimeController | None = None
        self._application.aboutToQuit.connect(self.shutdown)
        self._about_to_quit_connected = True

    def start(self) -> None:
        self.login_window.show()

    @Slot(object)
    def _open_dashboard(self, authentication: object) -> None:
        if not isinstance(authentication, AdminAuthentication):
            self.login_window.show_error(
                "A API retornou uma autenticação incompatível."
            )
            return

        session = self._session_context.open(authentication)
        self.main_window = MainWindow(session.administrator)
        self.dashboard_controller = DashboardController(
            self.main_window.dashboard,
            self._dashboard_service,
            self._session_context,
            shutdown_timeout_ms=self._settings.worker_shutdown_timeout_ms,
        )
        self.dashboard_controller.session_expired.connect(self._session_expired)
        self.dashboard_controller.shutdown_complete.connect(
            self._resume_pending_return_to_login
        )
        self.dashboard_controller.shutdown_complete.connect(
            self._finish_application_shutdown
        )
        self.realtime_controller = self._realtime_controller_factory(
            self._settings,
            self._session_context,
            self._auth_service,
            self.main_window,
            self.dashboard_controller.request_refresh,
        )
        self.realtime_controller.session_expired.connect(self._session_expired)
        self.realtime_controller.shutdown_complete.connect(
            self._resume_pending_return_to_login
        )
        self.realtime_controller.shutdown_complete.connect(
            self._finish_application_shutdown
        )
        self.main_window.logout_requested.connect(self.logout)

        self.main_window.show()
        self.login_window.hide()
        self.dashboard_controller.start()
        self.realtime_controller.start()
        logger.info(
            "Sessão administrativa iniciada",
            extra={"administrator_id": session.administrator.id},
        )

    @Slot()
    def logout(self) -> None:
        self._return_to_login("Sessão encerrada com segurança.")

    @Slot(str)
    def _session_expired(self, message: str) -> None:
        self._return_to_login(message)

    def _return_to_login(self, message: str) -> None:
        self._pending_login_message = message
        realtime_stopped = True
        if self.realtime_controller is not None:
            realtime_stopped = self.realtime_controller.shutdown()

        dashboard_stopped = True
        if self.dashboard_controller is not None:
            dashboard_stopped = self.dashboard_controller.shutdown()

        if not realtime_stopped or not dashboard_stopped:
            if self.main_window is not None:
                self.main_window.setEnabled(False)
            return

        self._complete_return_to_login(message)

    @Slot()
    def _resume_pending_return_to_login(self) -> None:
        message = self._pending_login_message
        if message is not None:
            self._return_to_login(message)

    def _complete_return_to_login(self, message: str) -> None:
        self._pending_login_message = None
        if self.realtime_controller is not None:
            self.realtime_controller.deleteLater()
            self.realtime_controller = None
        if self.dashboard_controller is not None:
            self.dashboard_controller.deleteLater()
            self.dashboard_controller = None

        if self.main_window is not None:
            self.main_window.hide()
            self.main_window.deleteLater()
            self.main_window = None

        self._session_context.clear()
        self.login_window.reset(message=message)
        self.login_window.show()
        self.login_window.raise_()
        self.login_window.activateWindow()

    @Slot()
    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True

        self._finish_application_shutdown()

    @Slot()
    def _finish_application_shutdown(self) -> None:
        if not self._shutting_down:
            return

        login_stopped = self.login_controller.shutdown()
        realtime_stopped = True
        if self.realtime_controller is not None:
            realtime_stopped = self.realtime_controller.shutdown()
        dashboard_stopped = True
        if self.dashboard_controller is not None:
            dashboard_stopped = self.dashboard_controller.shutdown()
        if login_stopped and realtime_stopped and dashboard_stopped:
            self._session_context.clear()
            self._api_client.close()
            self._disconnect_about_to_quit()
            logger.info("Cliente administrativo encerrado")
        else:
            logger.error(
                "Cliente HTTP preservado enquanto workers são encerrados"
            )

    def _disconnect_about_to_quit(self) -> None:
        if not self._about_to_quit_connected:
            return
        try:
            self._application.aboutToQuit.disconnect(self.shutdown)
        except (RuntimeError, TypeError):
            pass
        self._about_to_quit_connected = False
