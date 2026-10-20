"""Only conditions of Operator sessions that are still reporting drive the device tower."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from app.api.dependencies import get_db
from app.main import create_app
from app.models import SafetyAlertIngestion
from app.services import SessionLiveness
from tests.test_operator_alerts import (
    LifecycleDatabase,
    RecordingBroker,
    _api,
    _payload,
    make_settings,
)
from tests.test_ppe_inconclusive_tower import (
    _alert,
    _inconclusive,
    _resolved,
    _seed_operation,
    _snapshot,
)

DEVICE_TOKEN = "tower-test-token-at-least-32-random-bytes"
DEVICE_HEADERS = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
_TTL = 30.0


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _with_device(application, clock: FakeClock | None = None) -> None:
    application.state.settings = application.state.settings.model_copy(
        update={
            "safety_device_token": SecretStr(DEVICE_TOKEN),
            "realtime_heartbeat_interval_seconds": 0.05,
        }
    )
    if clock is not None:
        application.state.session_liveness = SessionLiveness(_TTL, clock=clock)


def _next_state(ws, expected: str, reason: str | None = None) -> dict[str, object]:
    # Heartbeats repeat the current state, so skip until the transition arrives.
    for _ in range(60):
        message = ws.receive_json()
        if message["state"] == expected and (reason is None or message["reason"] == reason):
            return message
    pytest.fail(f"{expected}/{reason} not delivered to the device")


def _fall(work_session_id: str) -> dict[str, object]:
    return _alert(
        work_session_id,
        violation_type="fall_detected",
        subject_key="fall:5",
        summary="Queda detectada",
        severity="critical",
    )


@pytest.fixture
def tower() -> Iterator[tuple[object, object, dict[str, str], FakeClock]]:
    fixture = _api()
    application, sessions, *_ = next(fixture)
    clock = FakeClock()
    _with_device(application, clock)
    _seed_operation(sessions)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    try:
        yield application, sessions, headers, clock
    finally:
        fixture.close()


def _put(client, headers, work_session_id: str, started_at: str, **fields) -> object:
    snapshot = _snapshot(work_session_id, started_at, {1: "confirmed", 2: "confirmed"}) | fields
    if fields.get("session_status") == "ended":
        snapshot["ppe"] = []
    return client.put("/operator/safety-state", json=snapshot, headers=headers)


def _api_sharing(sessions):
    """A fresh API process over the same database (models an API restart)."""

    application = create_app(
        settings=make_settings(),
        database=LifecycleDatabase(),
        realtime_event_broker=RecordingBroker(),
    )

    def override_get_db():
        with sessions() as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    return application


def test_unresolved_row_from_a_dead_session_does_not_drive_the_tower_after_restart() -> None:
    """Field report: old alerts kept the buzzer on with no current physical hazard."""

    fixture = _api()
    application, sessions, *_ = next(fixture)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    raised = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    fall = _payload() | {
        "violation_type": "fall_detected",
        "subject_key": "fall:1",
        "summary": "Queda detectada",
        "first_observed_at": raised,
        "raised_at": raised,
    }
    try:
        with TestClient(application) as client:
            # The Operator crashed after this alert: no resolution, no ended snapshot.
            assert client.post("/operator/alerts", json=fall, headers=headers).status_code == 201
        restarted = _api_sharing(sessions)
        _with_device(restarted)
        with (
            TestClient(restarted) as client,
            client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
        ):
            message = ws.receive_json()
            assert (message["state"], message["active_conditions"]) == ("GREEN", 0)
        with sessions() as session:
            # History is kept untouched for the Admin review and the cleanup decision.
            assert session.scalar(select(SafetyAlertIngestion.condicao_resolvida_em)) is None
    finally:
        fixture.close()


def test_fall_and_recovery_of_a_reporting_session(tower) -> None:
    application, _sessions, headers, _clock = tower
    work_session_id, started_at = str(uuid4()), datetime.now(UTC).isoformat()
    with (
        TestClient(application) as client,
        client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
    ):
        assert _next_state(ws, "GREEN")["active_conditions"] == 0
        assert _put(client, headers, work_session_id, started_at).status_code == 200
        fall = _fall(work_session_id)
        assert client.post("/operator/alerts", json=fall, headers=headers).status_code == 201
        assert _next_state(ws, "RED", "FALL_DETECTED")["active_conditions"] == 1
        # The worker stood up: physical recovery returns the tower to GREEN.
        resolved = _resolved(fall)
        assert client.post("/operator/alerts", json=resolved, headers=headers).status_code == 201
        assert _next_state(ws, "GREEN")["active_conditions"] == 0


def test_inconclusive_monitoring_is_yellow_while_the_session_reports(tower) -> None:
    application, _sessions, headers, _clock = tower
    work_session_id, started_at = str(uuid4()), datetime.now(UTC).isoformat()
    with (
        TestClient(application) as client,
        client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
    ):
        assert _put(client, headers, work_session_id, started_at).status_code == 200
        inconclusive = _inconclusive(work_session_id)
        response = client.post("/operator/alerts", json=inconclusive, headers=headers)
        assert response.status_code == 201
        message = _next_state(ws, "YELLOW", "MONITORING_INTERRUPTED")
        assert message["active_conditions"] == 1


def test_silent_session_leaves_the_tower_and_returns_when_it_reports_again(tower) -> None:
    application, sessions, headers, clock = tower
    work_session_id, started_at = str(uuid4()), datetime.now(UTC).isoformat()
    with (
        TestClient(application) as client,
        client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
    ):
        assert _put(client, headers, work_session_id, started_at).status_code == 200
        fall = _fall(work_session_id)
        assert client.post("/operator/alerts", json=fall, headers=headers).status_code == 201
        assert _next_state(ws, "RED", "FALL_DETECTED")
        # The Operator stops reporting (crash, power loss): after the TTL its unresolved
        # row is history and no longer sounds the buzzer.
        clock.now += _TTL + 1
        assert _next_state(ws, "GREEN")["active_conditions"] == 0
        with sessions() as session:
            assert session.scalar(select(SafetyAlertIngestion.condicao_resolvida_em)) is None
        # The same session comes back with the hazard unresolved: RED again.
        assert _put(client, headers, work_session_id, started_at).status_code == 200
        assert _next_state(ws, "RED", "FALL_DETECTED")["active_conditions"] == 1


def test_ended_session_clears_the_tower_even_after_configuration_change(tower) -> None:
    application, sessions, headers, _clock = tower
    work_session_id, started_at = str(uuid4()), datetime.now(UTC).isoformat()
    with (
        TestClient(application) as client,
        client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
    ):
        assert _put(client, headers, work_session_id, started_at).status_code == 200
        fall = _fall(work_session_id)
        assert client.post("/operator/alerts", json=fall, headers=headers).status_code == 201
        assert _next_state(ws, "RED", "FALL_DETECTED")
        # The Admin deactivates the operation while the session is running.
        with sessions.kw["bind"].begin() as connection:
            connection.execute(text("UPDATE operacoes SET ativa = 0"))
        ended = _put(client, headers, work_session_id, started_at, session_status="ended")
        assert ended.status_code == 409
        assert _next_state(ws, "GREEN")["active_conditions"] == 0
        with sessions() as session:
            assert session.scalar(select(SafetyAlertIngestion.condicao_resolvida_em))
        # A delayed retry of an alert raised before the end cannot revive the session.
        late = _fall(work_session_id) | {"subject_key": "fall:6"}
        assert client.post("/operator/alerts", json=late, headers=headers).status_code == 201
        assert client.portal.call(application.state.safety_state_aggregator.current).state == (
            "GREEN"
        )


def test_device_reconnect_receives_the_current_live_state(tower) -> None:
    application, _sessions, headers, _clock = tower
    work_session_id, started_at = str(uuid4()), datetime.now(UTC).isoformat()
    with TestClient(application) as client:
        assert _put(client, headers, work_session_id, started_at).status_code == 200
        fall = _fall(work_session_id)
        assert client.post("/operator/alerts", json=fall, headers=headers).status_code == 201
        for _ in range(2):
            with client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws:
                assert ws.receive_json()["state"] == "RED"
        resolved = _resolved(fall)
        assert client.post("/operator/alerts", json=resolved, headers=headers).status_code == 201
        with client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws:
            assert ws.receive_json()["state"] == "GREEN"


def test_session_liveness_tracks_reports_endings_and_expiry() -> None:
    clock = FakeClock()
    liveness = SessionLiveness(_TTL, clock=clock)
    session = uuid4()
    assert liveness.touch(7, session) is True
    assert liveness.touch(7, session) is False
    assert liveness.live_sessions() == {(7, session)}
    assert (8, session) not in liveness.live_sessions()
    clock.now += _TTL + 1
    assert liveness.live_sessions() == frozenset()
    assert liveness.prune_expired() is True
    assert liveness.prune_expired() is False
    assert liveness.touch(7, session) is True
    assert liveness.end(7, session) is True
    assert liveness.touch(7, session) is False
    assert liveness.live_sessions() == frozenset()
