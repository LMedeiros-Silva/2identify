"""Exercise the real controller, delivery worker and HTTP client together."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event

import httpx
import pytest

from app.core.config import AppSettings
from app.domain import CredentialAuthenticationResult, SafetyAlertSeverity
from app.engine.alert import AlertEngineUpdate
from app.workers.alert_delivery_worker import AlertDeliveryWorker
from tests.integration.test_application_controller import _setup_controller
from tests.unit.api.test_client import _client, _ergonomic_alert


@pytest.mark.parametrize("logout_immediately", [False, True])
def test_resolution_is_queued_after_inflight_raise_and_supersedes_escalation(
    qtbot,
    logout_immediately,
) -> None:
    started, release = Event(), Event()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            started.set()
            assert release.wait(5), "test did not release the first delivery"
        return httpx.Response(
            200,
            json={
                "event_id": payload["event_id"],
                "alert_id": 1,
                "occurrence_id": 2,
                "duplicate": False,
            },
        )

    client = _client(handler)
    _login, _session, controller = _setup_controller(qtbot)
    controller.handle_credential_authentication(
        CredentialAuthenticationResult(
            operator_id=15,
            name="Test operator",
            access_token="test-token",
        )
    )
    qtbot.addWidget(controller.main_window)
    # Inject transport after login so this test does not open a physical camera.
    controller._settings = AppSettings(_env_file=None)
    controller._alert_sender = client
    critical = _ergonomic_alert()
    warning = replace(
        critical,
        violation=replace(
            critical.violation,
            severity=SafetyAlertSeverity.WARNING,
        ),
    )
    resolved = critical.resolve(datetime(2026, 8, 23, 18, 1, tzinfo=UTC))
    try:
        controller._handle_local_alert_update(AlertEngineUpdate((warning,), (), (warning,)))
        qtbot.waitUntil(started.is_set)
        controller._handle_local_alert_update(AlertEngineUpdate((), (), (critical,), (critical,)))
        controller._handle_local_alert_update(AlertEngineUpdate((), (resolved,), ()))
        release.set()
        if logout_immediately:
            controller.handle_logout()
        qtbot.waitUntil(lambda: len(requests) == 2)
        qtbot.waitUntil(lambda: not controller._alert_delivery_workers)
        assert [item.get("status") for item in requests] == ["active", "resolved"]
        assert requests[1]["event_id"] == requests[0]["event_id"]
    finally:
        release.set()
        controller.shutdown()
        controller.handle_logout()
        client.close()


def test_logout_flushes_resolution_even_if_worker_has_not_started_sending(qtbot, monkeypatch):
    ready, release = Event(), Event()
    original_run = AlertDeliveryWorker.run
    original_interrupt = AlertDeliveryWorker.requestInterruption

    def delayed_run(worker):
        ready.set()
        assert release.wait(5)
        original_run(worker)

    def interrupt(worker):
        original_interrupt(worker)
        release.set()

    monkeypatch.setattr(AlertDeliveryWorker, "run", delayed_run)
    monkeypatch.setattr(AlertDeliveryWorker, "requestInterruption", interrupt)
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={
                "event_id": payload["event_id"],
                "alert_id": 1,
                "occurrence_id": 2,
                "duplicate": False,
            },
        )

    client = _client(handler)
    _login, _session, controller = _setup_controller(qtbot)
    controller.handle_credential_authentication(
        CredentialAuthenticationResult(
            operator_id=15,
            name="Test operator",
            access_token="test-token",
        )
    )
    qtbot.addWidget(controller.main_window)
    controller._settings = AppSettings(_env_file=None)
    controller._alert_sender = client
    resolved = _ergonomic_alert().resolve(datetime(2026, 8, 23, 18, 1, tzinfo=UTC))
    try:
        controller._handle_local_alert_update(AlertEngineUpdate((), (resolved,), ()))
        qtbot.waitUntil(ready.is_set)
        controller.handle_logout()
        assert [item["status"] for item in requests] == ["resolved"]
    finally:
        release.set()
        controller.shutdown()
        client.close()
