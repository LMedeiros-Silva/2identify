from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.controllers import dashboard_controller as dashboard_controller_module
from app.controllers.dashboard_controller import DashboardController
from app.core.session import AdminSessionContext
from app.domain import AdminAuthentication, Administrator
from app.services.admin_dashboard_service import AdminDashboardService
from app.ui.dashboard.dashboard_page import DashboardPage


class _UnusedDashboardProvider:
    def get_dashboard_summary(self, _access_token: str):
        raise AssertionError("O worker controlado não deve consultar o provider.")


class _ControlledDashboardWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str, bool)
    finished = Signal()
    instances: list[_ControlledDashboardWorker] = []

    def __init__(self, _service, _session) -> None:
        super().__init__()
        self.running = False
        self.interrupted = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        self.running = True

    def isRunning(self) -> bool:
        return self.running

    def requestInterruption(self) -> None:
        self.interrupted = True

    def wait(self, _timeout_ms: int) -> bool:
        self.running = False
        return True

    def complete(self) -> None:
        self.running = False
        self.finished.emit()


def _session_context() -> AdminSessionContext:
    context = AdminSessionContext()
    context.open(
        AdminAuthentication(
            administrator=Administrator(
                id=1,
                name="Admin",
                username="admin",
                profile="administrador",
            ),
            access_token="token-efemero",
            expires_in=300,
        )
    )
    return context


def test_refresh_requested_during_load_is_coalesced_and_runs_after_finish(
    qapp, monkeypatch
) -> None:
    _ControlledDashboardWorker.instances.clear()
    monkeypatch.setattr(
        dashboard_controller_module,
        "DashboardSummaryWorker",
        _ControlledDashboardWorker,
    )
    page = DashboardPage()
    controller = DashboardController(
        page,
        AdminDashboardService(_UnusedDashboardProvider()),
        _session_context(),
        shutdown_timeout_ms=100,
    )

    controller.request_refresh()
    controller.request_refresh()
    controller.request_refresh()
    assert len(_ControlledDashboardWorker.instances) == 1

    _ControlledDashboardWorker.instances[0].complete()
    qapp.processEvents()
    qapp.processEvents()

    assert len(_ControlledDashboardWorker.instances) == 2
    _ControlledDashboardWorker.instances[1].complete()
    qapp.processEvents()
    assert controller.shutdown()
    page.deleteLater()
