"""The physical tower must follow persisted alert lifecycle, not volatile snapshots."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.testclient import WebSocketDenialResponse

from app.api.dependencies import get_current_operator
from app.repositories.safety_alert_repository import SafetyAlertRepository
from app.services import OperatorPrincipal
from tests.test_admin_alerts import _alert_api, _token
from tests.test_operator_alerts import _api, _payload

DEVICE_TOKEN = "tower-test-token-at-least-32-random-bytes"


def current(client, application):
    state = client.portal.call(application.state.safety_state_aggregator.current)
    assert state is not None, "Tower state must be calculated from persisted alerts"
    return state


def test_tower_tracks_persisted_priority_and_automatic_resolution() -> None:
    fixture = _api()
    application, _sessions, _broker, _occurrences, _alerts = next(fixture)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    warning = _payload() | {"severity": "warning"}
    critical = _payload()
    try:
        with TestClient(application) as client:
            assert client.post("/operator/alerts", json=warning, headers=headers).status_code == 201
            assert current(client, application).state == "YELLOW"
            assert (
                client.post("/operator/alerts", json=critical, headers=headers).status_code == 201
            )
            assert current(client, application).state == "RED"
            assert current(client, application).active_conditions == 2
            resolved = critical | {
                "status": "resolved",
                "resolved_at": datetime.now(UTC).isoformat(),
            }
            assert (
                client.post("/operator/alerts", json=resolved, headers=headers).status_code == 201
            )
            assert current(client, application).state == "YELLOW"
            assert current(client, application).active_conditions == 1
            # An out-of-order retry may not reopen a resolved hazard.
            assert (
                client.post("/operator/alerts", json=critical, headers=headers).status_code == 200
            )
            assert current(client, application).state == "YELLOW"
            warning |= {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
            assert client.post("/operator/alerts", json=warning, headers=headers).status_code == 201
            assert current(client, application).state == "GREEN"
            assert current(client, application).active_conditions == 0
    finally:
        fixture.close()


def test_device_boot_and_reconnect_load_existing_critical_and_admin_closure() -> None:
    fixture = _alert_api()
    application, _sessions, _alerts = next(fixture)
    application.state.settings = application.state.settings.model_copy(
        update={"safety_device_token": SecretStr(DEVICE_TOKEN)}
    )
    device_headers = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
    try:
        with TestClient(application) as client:
            headers = {"Authorization": f"Bearer {_token(client)}"}
            with client.websocket_connect("/ws/devices/safety", headers=device_headers) as ws:
                # This assertion avoids hanging when the old endpoint sends no initial state.
                assert current(client, application).state == "RED"
                assert ws.receive_json()["state"] == "RED"
                assert (
                    client.patch("/admin/alerts/20/confirm", json={}, headers=headers).status_code
                    == 200
                )
                assert current(client, application).state == "RED"
                assert (
                    client.patch("/admin/alerts/20/close", json={}, headers=headers).status_code
                    == 200
                )
                assert ws.receive_json()["state"] == "GREEN"
            with client.websocket_connect("/ws/devices/safety", headers=device_headers) as ws:
                assert ws.receive_json()["state"] == "GREEN"
    finally:
        fixture.close()


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_device_rejects_unauthenticated_connections(token: str | None) -> None:
    fixture = _api()
    application, *_ = next(fixture)
    application.state.settings = application.state.settings.model_copy(
        update={"safety_device_token": SecretStr(DEVICE_TOKEN)}
    )
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    try:
        with TestClient(application) as client:
            with (
                pytest.raises(WebSocketDenialResponse) as denied,
                client.websocket_connect("/ws/devices/safety", headers=headers),
            ):
                pass
            assert denied.value.status_code == 401
    finally:
        fixture.close()


def test_new_device_receives_green_without_operator_initialization() -> None:
    fixture = _api()
    application, *_ = next(fixture)
    application.state.settings = application.state.settings.model_copy(
        update={"safety_device_token": SecretStr(DEVICE_TOKEN)}
    )
    try:
        with (
            TestClient(application) as client,
            client.websocket_connect(
                "/ws/devices/safety", headers={"Authorization": f"Bearer {DEVICE_TOKEN}"}
            ) as ws,
        ):
            assert current(client, application).state == "GREEN"
            payload = ws.receive_json()
            assert payload["state"] == "GREEN"
            assert payload["active_conditions"] == 0
    finally:
        fixture.close()


def test_websocket_receives_escalation_resolution_and_application_heartbeat() -> None:
    fixture = _api()
    application, _sessions, broker, *_ = next(fixture)
    application.state.settings = application.state.settings.model_copy(
        update={
            "safety_device_token": SecretStr(DEVICE_TOKEN),
            "realtime_heartbeat_interval_seconds": 0.1,
        }
    )
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    warning = _payload() | {"severity": "warning"}
    try:
        with TestClient(application) as client:
            with client.websocket_connect(
                "/ws/devices/safety", headers={"Authorization": f"Bearer {DEVICE_TOKEN}"}
            ) as ws:
                first = ws.receive_json()
                assert first["state"] == "GREEN"
                assert ws.receive_json() == first  # Application heartbeat, no new alert.
                for payload, expected in [
                    (warning, "YELLOW"),
                    (warning | {"severity": "critical"}, "RED"),
                    (
                        warning
                        | {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()},
                        "GREEN",
                    ),
                ]:
                    assert (
                        client.post("/operator/alerts", json=payload, headers=headers).status_code
                        == 201
                    )
                    assert current(client, application).state == expected
                    # A heartbeat for the previous state can already be queued.
                    for _ in range(10):
                        if ws.receive_json()["state"] == expected:
                            break
                    else:
                        pytest.fail("state transition not delivered to hardware")
            assert len({event.event_id for event in broker.published}) == 3
            assert broker.published[-1].payload.status == "encerrado"
    finally:
        fixture.close()


def test_legacy_empty_snapshot_cannot_clear_persisted_critical_alert() -> None:
    fixture = _api()
    application, *_ = next(fixture)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    payload = _payload()
    try:
        with TestClient(application) as client:
            assert client.post("/operator/alerts", json=payload, headers=headers).status_code == 201
            snapshot = {
                key: payload[key] for key in ("work_session_id", "operation_id", "camera_id")
            }
            snapshot |= {"observed_at": datetime.now(UTC).isoformat(), "conditions": []}
            response = client.put("/operator/safety-state", json=snapshot, headers=headers)
            assert response.status_code == 200
            assert response.json()["state"] == "RED"
    finally:
        fixture.close()


def test_operator_cannot_resolve_another_accounts_event() -> None:
    fixture = _api()
    application, *_ = next(fixture)
    payload = _payload()
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    try:
        with TestClient(application) as client:
            assert client.post("/operator/alerts", json=payload, headers=headers).status_code == 201
            application.dependency_overrides[get_current_operator] = lambda: OperatorPrincipal(
                account_id=99,
                name="Other operator",
                profile="operador",
            )
            response = client.post(
                "/operator/alerts",
                json=payload
                | {
                    "status": "resolved",
                    "resolved_at": datetime.now(UTC).isoformat(),
                },
                headers=headers,
            )
            assert response.status_code == 409
            assert current(client, application).state == "RED"
    finally:
        fixture.close()


@pytest.mark.parametrize(
    "transition",
    [
        {"status": "resolved"},
        {"status": "active", "resolved_at": "2026-01-01T00:00:00Z"},
        {"status": "resolved", "resolved_at": "2000-01-01T00:00:00Z"},
    ],
)
def test_invalid_resolution_timeline_is_rejected(transition) -> None:
    fixture = _api()
    application, *_ = next(fixture)
    try:
        with TestClient(application) as client:
            response = client.post(
                "/operator/alerts",
                json=_payload() | transition,
                headers={"Authorization": f"Bearer {application.state.test_token}"},
            )
            assert response.status_code == 422
    finally:
        fixture.close()


def test_device_database_failure_is_not_reported_as_green() -> None:
    fixture = _api()
    application, sessions, _broker, _occurrences, alerts = next(fixture)
    application.state.settings = application.state.settings.model_copy(
        update={
            "safety_device_token": SecretStr(DEVICE_TOKEN),
        }
    )
    try:
        alerts.drop(sessions.kw["bind"])
        with TestClient(application) as client:
            with (
                pytest.raises(WebSocketDenialResponse) as denied,
                client.websocket_connect(
                    "/ws/devices/safety", headers={"Authorization": f"Bearer {DEVICE_TOKEN}"}
                ),
            ):
                pass
            assert denied.value.status_code == 503
    finally:
        fixture.close()


def test_coalesced_critical_resolution_preserves_highest_persisted_severity() -> None:
    fixture = _api()
    application, sessions, _broker, _occurrences, alerts = next(fixture)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    warning = _payload() | {"severity": "warning"}
    try:
        with TestClient(application) as client:
            assert client.post("/operator/alerts", json=warning, headers=headers).status_code == 201
            assert (
                client.post(
                    "/operator/alerts",
                    json=warning
                    | {
                        "severity": "critical",
                        "status": "resolved",
                        "resolved_at": datetime.now(UTC).isoformat(),
                    },
                    headers=headers,
                ).status_code
                == 201
            )
            with sessions() as session:
                assert session.execute(select(alerts.c.nivel, alerts.c.status)).one() == (
                    "critico",
                    "encerrado",
                )
    finally:
        fixture.close()


def test_tower_refresh_failure_does_not_lose_committed_admin_notification(monkeypatch) -> None:
    fixture = _api()
    application, _sessions, broker, *_ = next(fixture)
    original = SafetyAlertRepository.active_conditions
    calls = 0

    def intermittent_failure(repository):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError("test select", {}, Exception("database unavailable"))
        return original(repository)

    monkeypatch.setattr(SafetyAlertRepository, "active_conditions", intermittent_failure)
    payload = _payload()
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    try:
        with TestClient(application) as client:
            first = client.post("/operator/alerts", json=payload, headers=headers)
            assert first.status_code == 201
            assert client.portal.call(application.state.safety_state_aggregator.current) is None
            assert len(broker.published) == 1
            assert client.post("/operator/alerts", json=payload, headers=headers).status_code == 200
            assert len(broker.published) == 1
            assert current(client, application).state == "RED"
    finally:
        fixture.close()
