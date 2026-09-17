from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from threading import Event
from uuid import uuid4

import httpx
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QLabel
from test_ppe_management_ui import _snapshot
from test_realtime_controller import (
    FakeWebSocket,
    administrator,
    build_controller,
    ready_event,
    session_context,
    settings,
    wait_until,
)

from app.api import AdminApiClient
from app.controllers.ppe_management_controller import PpeManagementController
from app.domain.ppe_management import WorkSessionLiveStatus
from app.services.admin_ppe_management_service import AdminPpeManagementService
from app.services.errors import ApiUnavailableError, InvalidApiResponseError, SessionExpiredError
from app.ui.main.main_window import MainWindow
from app.ui.ppe import PpeManagementPage
from app.workers.ppe_management_worker import PpeManagementWorker


@pytest.mark.parametrize("status", [401, 403])
def test_snapshot_rejects_unauthorized_session(status):
    with AdminApiClient(
        settings(), transport=httpx.MockTransport(lambda _: httpx.Response(status))
    ) as client:
        with pytest.raises(SessionExpiredError):
            client.get_active_operations("token")


@pytest.mark.parametrize("payload", [{}, [None], [{"work_session_id": "invalid"}]])
def test_snapshot_rejects_malformed_payload(payload):
    with AdminApiClient(
        settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(InvalidApiResponseError):
            client.get_active_operations("token")


def test_http_snapshot_cannot_resurrect_session_ended_during_load(qapp):
    release, entered = Event(), Event()

    class Provider:
        def get_active_operations(self, token):
            assert token == "secret.jwt.value"
            entered.set()
            assert release.wait(3)
            return (_snapshot(),)

    page = PpeManagementPage()
    controller = PpeManagementController(
        page, AdminPpeManagementService(Provider()), session_context(), shutdown_timeout_ms=3000
    )
    try:
        controller.start()
        wait_until(qapp, entered.is_set)
        ended = _snapshot(status=WorkSessionLiveStatus.ENDED)
        controller.apply_update(ended)
        release.set()
        wait_until(qapp, lambda: not controller.is_loading)
        assert page.card_count == 0
    finally:
        release.set()
        assert controller.shutdown()
        page.close()


def test_failed_refresh_preserves_snapshot_and_expiration_is_signalled(qapp):
    class Provider:
        failure = ApiUnavailableError

        def get_active_operations(self, token):
            raise self.failure("unavailable")

    provider = Provider()
    page = PpeManagementPage()
    page.show_snapshot((_snapshot(),))
    controller = PpeManagementController(
        page, AdminPpeManagementService(provider), session_context(), shutdown_timeout_ms=3000
    )
    expired = QSignalSpy(controller.session_expired)
    try:
        controller.request_refresh()
        wait_until(qapp, lambda: not controller.is_loading)
        assert page.card_count == 1
        assert expired.count() == 0
        provider.failure = SessionExpiredError
        controller.request_refresh()
        wait_until(qapp, lambda: not controller.is_loading)
        assert expired.count() == 1
    finally:
        assert controller.shutdown()
        page.close()


def test_interrupted_snapshot_worker_suppresses_late_result(qapp):
    entered, release = Event(), Event()

    class Provider:
        def get_active_operations(self, token):
            entered.set()
            assert release.wait(3)
            return (_snapshot(),)

    worker = PpeManagementWorker(AdminPpeManagementService(Provider()), session_context().current())
    success = QSignalSpy(worker.succeeded)
    try:
        worker.start()
        assert entered.wait(3)
        worker.requestInterruption()
    finally:
        release.set()
        assert worker.wait(3000)
    qapp.processEvents()
    assert success.count() == 0


def test_ready_and_reconnect_request_authoritative_snapshot(qapp):
    view = MainWindow(administrator())
    socket = FakeWebSocket()
    controller = build_controller(
        socket=socket, context=session_context(), view=view, refresh=lambda: None
    )
    requests = QSignalSpy(view.ppe_snapshot_requested)
    try:
        controller.start()
        socket.simulate_connected()
        socket.textMessageReceived.emit(ready_event())
        assert requests.count() == 1
        socket.simulate_disconnected()
        socket.simulate_connected()
        socket.textMessageReceived.emit(ready_event())
        assert requests.count() == 2
    finally:
        controller.shutdown()
        view.close()


def test_older_event_cannot_replace_newer_state_or_resurrect_ended_session(qapp):
    page = PpeManagementPage()
    old = _snapshot()
    new = replace(
        old, operator_name="Atualizado", observed_at=old.observed_at + timedelta(seconds=5)
    )
    page.apply_update(new)
    page.apply_update(old)
    assert "Atualizado" in page.cards_text()
    page.apply_update(replace(new, session_status=WorkSessionLiveStatus.ENDED))
    page.apply_update(old)
    assert page.card_count == 0
    page.close()


def test_empty_http_refresh_preserves_ended_session_ordering(qapp):
    page = PpeManagementPage()
    old = _snapshot()
    ended = replace(old, session_status=WorkSessionLiveStatus.ENDED)
    page.apply_update(ended)
    page.show_snapshot(())
    page.apply_update(old)
    assert page.card_count == 0
    page.close()


def test_update_of_other_operator_preserves_card_text_selection(qapp):
    page = PpeManagementPage()
    first = _snapshot()
    second = replace(first, operator_id=22, work_session_id=uuid4(), operator_name="Outra pessoa")
    page.show_snapshot((first, second))
    name = next(label for label in page.findChildren(QLabel) if "Breno" in label.text())
    name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    name.setSelection(3, 5)
    assert name.selectedText() == "Breno"
    page.apply_update(replace(second, observed_at=second.observed_at + timedelta(seconds=1)))
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    name = next(label for label in page.findChildren(QLabel) if "Breno" in label.text())
    assert name.selectedText() == "Breno"
    page.close()


def test_summary_counts_operator_once_across_two_sessions(qapp):
    page = PpeManagementPage()
    first = _snapshot()
    page.show_snapshot((first, replace(first, work_session_id=uuid4())))
    assert page.online_count_label.text() == "1"
    assert page.alert_count_label.text() == "1"
    page.close()
