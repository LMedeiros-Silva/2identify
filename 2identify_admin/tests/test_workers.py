from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event

import httpx
from PySide6.QtTest import QSignalSpy

from app.api import AdminApiClient
from app.core.config import Settings
from app.core.session import AdminSession
from app.domain import (
    AdminAuthentication,
    AdminCredentials,
    Administrator,
    DashboardSummary,
)
from app.services.admin_alerts_service import AdminAlertsService
from app.services.errors import SessionExpiredError
from app.workers import AdminAlertsListWorker, AdminLoginWorker, DashboardSummaryWorker


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


def test_alert_worker_reports_invalid_api_response_separately_from_connection(qapp) -> None:
    session = AdminSession(
        administrator=administrator(),
        access_token="test-token",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    settings = Settings(_env_file=None, API_URL="https://api.example.test")
    with AdminApiClient(
        settings,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"unexpected": "private-payload"})
        ),
    ) as client:
        worker = AdminAlertsListWorker(AdminAlertsService(client), session)
        failure = QSignalSpy(worker.failed)
        worker.start()
        assert worker.wait(2_000)
        qapp.processEvents()

    assert failure.count() == 1
    message, expired = failure.at(0)
    assert "incompatív" in message
    assert "conexão" not in message
    assert "private-payload" not in message
    assert expired is False
