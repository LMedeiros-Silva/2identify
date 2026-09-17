from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication

from app.api import AdminApiClient
from app.controllers.alerts_controller import AlertsController
from app.controllers.dashboard_controller import DashboardController
from app.controllers.employees_controller import EmployeesController
from app.controllers.login_controller import LoginController
from app.controllers.operations_controller import OperationsController
from app.controllers.ppe_management_controller import PpeManagementController
from app.controllers.realtime_controller import RealtimeController
from app.controllers.reports_controller import ReportsController
from app.core.config import Settings
from app.core.session import AdminSessionContext
from app.domain import AdminAuthentication
from app.services.admin_alerts_service import AdminAlertsService
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.admin_employees_service import AdminEmployeesService
from app.services.admin_operations_service import AdminOperationsService
from app.services.admin_ppe_management_service import AdminPpeManagementService
from app.services.admin_reports_service import AdminReportsService
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
        self._alerts_service = AdminAlertsService(api_client)
        self._dashboard_service = AdminDashboardService(api_client)
        self._operations_service = AdminOperationsService(api_client)
        self._ppe_service = AdminPpeManagementService(api_client)
        self._reports_service = AdminReportsService(api_client)
        self._employees_service = AdminEmployeesService(api_client)
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
        self.alerts_controller: AlertsController | None = None
        self.operations_controller: OperationsController | None = None
        self.ppe_controller: PpeManagementController | None = None
        self.realtime_controller: RealtimeController | None = None
        self.reports_controller: ReportsController | None = None
        self.employees_controller: EmployeesController | None = None
        self._application.aboutToQuit.connect(self.shutdown)
        self._about_to_quit_connected = True

    def start(self) -> None:
        self.login_window.show()

    @Slot(object)
    def _open_dashboard(self, authentication: object) -> None:
        if not isinstance(authentication, AdminAuthentication):
            self.login_window.show_error("A API retornou uma autenticação incompatível.")
            return

        session = self._session_context.open(authentication)
        self.main_window = MainWindow(session.administrator, self._settings)
        self.dashboard_controller = DashboardController(
            self.main_window.dashboard,
            self._dashboard_service,
            self._session_context,
            shutdown_timeout_ms=self._settings.worker_shutdown_timeout_ms,
        )
        self.dashboard_controller.session_expired.connect(self._session_expired)
        self.dashboard_controller.shutdown_complete.connect(self._resume_pending_return_to_login)
        self.dashboard_controller.shutdown_complete.connect(self._finish_application_shutdown)
        self.alerts_controller = AlertsController(
            self.main_window.alerts,
            self._alerts_service,
            self._session_context,
            shutdown_timeout_ms=self._settings.worker_shutdown_timeout_ms,
        )
        self.alerts_controller.session_expired.connect(self._session_expired)
        self.alerts_controller.alerts_changed.connect(self.dashboard_controller.request_refresh)
        self.alerts_controller.shutdown_complete.connect(self._resume_pending_return_to_login)
        self.alerts_controller.shutdown_complete.connect(self._finish_application_shutdown)
        self.operations_controller = OperationsController(
            self.main_window.operations,
            self._operations_service,
            self._session_context,
            shutdown_timeout_ms=self._settings.worker_shutdown_timeout_ms,
        )
        self.operations_controller.session_expired.connect(self._session_expired)
        self.operations_controller.shutdown_complete.connect(self._resume_pending_return_to_login)
        self.operations_controller.shutdown_complete.connect(self._finish_application_shutdown)
        self.ppe_controller = PpeManagementController(
            self.main_window.ppe_management,
            self._ppe_service,
            self._session_context,
            shutdown_timeout_ms=self._settings.worker_shutdown_timeout_ms,
        )
        self.ppe_controller.session_expired.connect(self._session_expired)
        self.ppe_controller.shutdown_complete.connect(self._resume_pending_return_to_login)
        self.ppe_controller.shutdown_complete.connect(self._finish_application_shutdown)
        self.reports_controller = ReportsController(
            self.main_window.reports,
            self._reports_service,
            self._session_context,
            shutdown_timeout_ms=self._settings.worker_shutdown_timeout_ms,
        )
        self.reports_controller.session_expired.connect(self._session_expired)
        self.reports_controller.shutdown_complete.connect(self._resume_pending_return_to_login)
        self.reports_controller.shutdown_complete.connect(self._finish_application_shutdown)
        self.employees_controller = EmployeesController(
            self.main_window.employees,
            self._employees_service,
            self._session_context,
            shutdown_timeout_ms=self._settings.worker_shutdown_timeout_ms,
        )
        self.employees_controller.session_expired.connect(self._session_expired)
        self.employees_controller.shutdown_complete.connect(self._resume_pending_return_to_login)
        self.employees_controller.shutdown_complete.connect(self._finish_application_shutdown)
        self.main_window.ppe_snapshot_requested.connect(self.ppe_controller.request_refresh)
        self.main_window.ppe_session_updated.connect(self.ppe_controller.apply_update)
        self.realtime_controller = self._realtime_controller_factory(
            self._settings,
            self._session_context,
            self._auth_service,
            self.main_window,
            self.dashboard_controller.request_refresh,
        )
        self.realtime_controller.session_expired.connect(self._session_expired)
        self.realtime_controller.shutdown_complete.connect(self._resume_pending_return_to_login)
        self.realtime_controller.shutdown_complete.connect(self._finish_application_shutdown)
        self.main_window.logout_requested.connect(self.logout)
        self.main_window.realtime_alert_received.connect(self.alerts_controller.request_refresh)

        self.main_window.show()
        self.login_window.hide()
        self.dashboard_controller.start()
        self.alerts_controller.start()
        self.operations_controller.start()
        self.ppe_controller.start()
        self.employees_controller.start()
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

        alerts_stopped = True
        if self.alerts_controller is not None:
            alerts_stopped = self.alerts_controller.shutdown()

        operations_stopped = True
        if self.operations_controller is not None:
            operations_stopped = self.operations_controller.shutdown()

        ppe_stopped = self.ppe_controller is None or self.ppe_controller.shutdown()
        reports_stopped = self.reports_controller is None or self.reports_controller.shutdown()
        employees_stopped = (
            self.employees_controller is None or self.employees_controller.shutdown()
        )

        if (
            not realtime_stopped
            or not dashboard_stopped
            or not alerts_stopped
            or not operations_stopped
            or not ppe_stopped
            or not reports_stopped
            or not employees_stopped
        ):
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
        if self.alerts_controller is not None:
            self.alerts_controller.deleteLater()
            self.alerts_controller = None
        if self.operations_controller is not None:
            self.operations_controller.deleteLater()
            self.operations_controller = None
        if self.ppe_controller is not None:
            self.ppe_controller.deleteLater()
            self.ppe_controller = None
        if self.reports_controller is not None:
            self.reports_controller.deleteLater()
            self.reports_controller = None
        if self.employees_controller is not None:
            self.employees_controller.deleteLater()
            self.employees_controller = None

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
        alerts_stopped = True
        if self.alerts_controller is not None:
            alerts_stopped = self.alerts_controller.shutdown()
        operations_stopped = True
        if self.operations_controller is not None:
            operations_stopped = self.operations_controller.shutdown()
        ppe_stopped = self.ppe_controller is None or self.ppe_controller.shutdown()
        reports_stopped = self.reports_controller is None or self.reports_controller.shutdown()
        employees_stopped = (
            self.employees_controller is None or self.employees_controller.shutdown()
        )
        if (
            login_stopped
            and realtime_stopped
            and dashboard_stopped
            and alerts_stopped
            and operations_stopped
            and ppe_stopped
            and reports_stopped
            and employees_stopped
        ):
            self._session_context.clear()
            self._api_client.close()
            self._disconnect_about_to_quit()
            logger.info("Cliente administrativo encerrado")
        else:
            logger.error("Cliente HTTP preservado enquanto workers são encerrados")

    def _disconnect_about_to_quit(self) -> None:
        if not self._about_to_quit_connected:
            return
        try:
            self._application.aboutToQuit.disconnect(self.shutdown)
        except (RuntimeError, TypeError):
            pass
        self._about_to_quit_connected = False
