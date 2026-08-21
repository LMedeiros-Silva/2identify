from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event

from PySide6.QtTest import QSignalSpy

from app.core.session import AdminSession
from app.domain import (
    AdminAuthentication,
    AdminCredentials,
    Administrator,
    DashboardSummary,
)
from app.services.errors import SessionExpiredError
from app.workers import AdminLoginWorker, DashboardSummaryWorker


def administrator() -> Administrator:
    return Administrator(
        id=2,
        name="Admin Teste",
        username="admin",
        profile="administrador",
    )


class SuccessfulAuthService:
    def authenticate(self, _credentials: AdminCredentials) -> AdminAuthentication:
        return AdminAuthentication(
            administrator=administrator(),
            access_token="token",
            expires_in=60,
        )


class ExpiredDashboardService:
    def get_summary(self, _access_token: str) -> DashboardSummary:
        raise SessionExpiredError("expired")


class BlockingAuthService:
    def __init__(self, release: Event) -> None:
        self.release = release

    def authenticate(self, _credentials: AdminCredentials) -> AdminAuthentication:
        self.release.wait(timeout=2)
        return AdminAuthentication(
            administrator=administrator(),
            access_token="token",
            expires_in=60,
        )


def test_login_worker_emits_success_off_ui_thread(qapp) -> None:
    worker = AdminLoginWorker(
        SuccessfulAuthService(),  # type: ignore[arg-type]
        AdminCredentials("admin", "senha-segura"),
    )
    spy = QSignalSpy(worker.succeeded)
    worker.start()
    assert worker.wait(2_000)
    qapp.processEvents()

    assert spy.count() == 1
    assert isinstance(spy.at(0)[0], AdminAuthentication)


def test_dashboard_worker_marks_unauthorized_as_expired(qapp) -> None:
    session = AdminSession(
        administrator=administrator(),
        access_token="token",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    worker = DashboardSummaryWorker(
        ExpiredDashboardService(),  # type: ignore[arg-type]
        session,
    )
    spy = QSignalSpy(worker.failed)
    worker.start()
    assert worker.wait(2_000)
    qapp.processEvents()

    assert spy.count() == 1
    assert spy.at(0)[1] is True


def test_interrupted_login_worker_does_not_emit_late_result(qapp) -> None:
    release = Event()
    worker = AdminLoginWorker(
        BlockingAuthService(release),  # type: ignore[arg-type]
        AdminCredentials("admin", "senha-segura"),
    )
    success_spy = QSignalSpy(worker.succeeded)
    failure_spy = QSignalSpy(worker.failed)
    worker.start()
    worker.requestInterruption()
    release.set()
    assert worker.wait(2_000)
    qapp.processEvents()

    assert success_spy.count() == 0
    assert failure_spy.count() == 0
