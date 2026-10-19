"""Physical hazard lifecycle (tower) is independent from the Admin review lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.api.dependencies import get_current_admin, get_current_operator
from app.models import PERSISTED_SAFETY_ALERTS, SafetyAlertIngestion, Usuario
from app.services import AdministratorPrincipal, OperatorPrincipal
from tests.test_admin_alerts import _alert_api, _token
from tests.test_operator_alerts import _api
from tests.test_ppe_inconclusive_tower import _seed_operation, _snapshot

DEVICE_TOKEN = "tower-test-token-at-least-32-random-bytes"
DEVICE_HEADERS = {"Authorization": f"Bearer {DEVICE_TOKEN}"}


def _with_device(application) -> None:
    application.state.settings = application.state.settings.model_copy(
        update={
            "safety_device_token": SecretStr(DEVICE_TOKEN),
            "realtime_heartbeat_interval_seconds": 0.05,
        }
    )


def _next_state(ws, expected: str, reason: str | None = None) -> dict[str, object]:
    for _ in range(40):
        message = ws.receive_json()
        if message["state"] == expected and (reason is None or message["reason"] == reason):
            return message
    pytest.fail(f"{expected}/{reason} not delivered to the device")


def _alert(work_session_id: str, operation_id: int, **fields) -> dict[str, object]:
    timestamp = datetime.now(UTC).isoformat()
    return {
        "event_id": str(uuid4()),
        "work_session_id": work_session_id,
        "operation_id": operation_id,
        "camera_id": 5,
        "risk_area_id": None,
        "violation_type": "ppe_absent",
        "subject_key": "ppe:1",
        "summary": "EPI obrigatório ausente: Capacete",
        "severity": "critical",
        "status": "active",
        "resolved_at": None,
        "first_observed_at": timestamp,
        "raised_at": timestamp,
        **fields,
    }


def _resolved(payload: dict[str, object]) -> dict[str, object]:
    return payload | {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}


def _operator_review_api():
    """Admin review fixture whose seeded alert has no Operator physical lifecycle."""

    fixture = _alert_api(include_ingestion=False)
    application, sessions, alerts = next(fixture)
    _with_device(application)
    with sessions() as session:
        operator_id = session.scalar(select(Usuario.id).where(Usuario.username == "operador"))
    application.dependency_overrides[get_current_operator] = lambda: OperatorPrincipal(
        account_id=operator_id, name="Operador Ergonomia", profile="operador"
    )
    return fixture, application, sessions, alerts


def test_admin_closure_does_not_hide_an_active_physical_condition() -> None:
    fixture, application, sessions, alerts = _operator_review_api()
    payload = _alert(str(uuid4()), 12)
    try:
        with (
            TestClient(application) as client,
            client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
        ):
            # The legacy Admin alert #20 has no physical lifecycle: it cannot hold the tower.
            assert _next_state(ws, "GREEN")["active_conditions"] == 0
            admin = {"Authorization": f"Bearer {_token(client)}"}
            created = client.post("/operator/alerts", json=payload)
            assert created.status_code == 201
            alert_id = created.json()["alert_id"]
            assert _next_state(ws, "RED", "PPE_MISSING")["active_conditions"] == 1

            assert (
                client.patch(
                    f"/admin/alerts/{alert_id}/confirm", json={}, headers=admin
                ).status_code
                == 200
            )
            closed = client.patch(f"/admin/alerts/{alert_id}/close", json={}, headers=admin)
            assert closed.status_code == 200
            assert closed.json()["status"] == "encerrado"
            # The hazard is still physically present.
            assert _next_state(ws, "RED")["active_conditions"] == 1

            assert client.post("/operator/alerts", json=_resolved(payload)).status_code == 201
            assert _next_state(ws, "GREEN")["active_conditions"] == 0

        with sessions() as session:
            row = session.execute(
                select(
                    alerts.c.status,
                    alerts.c.encerrado_por,
                    alerts.c.encerrado_em,
                    alerts.c.criado_em,
                    SafetyAlertIngestion.condicao_resolvida_em,
                )
                .join(SafetyAlertIngestion, SafetyAlertIngestion.alerta_id == alerts.c.id)
                .where(alerts.c.id == alert_id)
            ).one()
        assert row.status == "encerrado"
        assert row.encerrado_por == application.state.test_admin_id
        assert row.encerrado_em is not None and row.criado_em is not None
        assert row.condicao_resolvida_em is not None
    finally:
        fixture.close()


def test_physical_resolution_returns_green_and_keeps_alert_for_admin_review() -> None:
    fixture, application, sessions, alerts = _operator_review_api()
    payload = _alert(str(uuid4()), 12, violation_type="ergonomic_risk", subject_key="trunk")
    try:
        with (
            TestClient(application) as client,
            client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
        ):
            _next_state(ws, "GREEN")
            admin = {"Authorization": f"Bearer {_token(client)}"}
            alert_id = client.post("/operator/alerts", json=payload).json()["alert_id"]
            _next_state(ws, "RED", "ERGONOMIC_RISK")
            assert client.post("/operator/alerts", json=_resolved(payload)).status_code == 201
            assert _next_state(ws, "GREEN")["active_conditions"] == 0
            # A retried resolution is idempotent and creates nothing new.
            retry = client.post("/operator/alerts", json=_resolved(payload))
            assert retry.status_code == 200 and retry.json()["duplicate"] is True

            pending = client.get(f"/admin/alerts/{alert_id}", headers=admin)
            assert pending.status_code == 200
            assert pending.json()["status"] == "nao_lido"
            assert (
                client.patch(
                    f"/admin/alerts/{alert_id}/confirm", json={}, headers=admin
                ).status_code
                == 200
            )
            assert (
                client.patch(f"/admin/alerts/{alert_id}/close", json={}, headers=admin).status_code
                == 200
            )
            assert (
                client.portal.call(application.state.safety_state_aggregator.current).state
                == "GREEN"
            )

        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(alerts)) == 2
    finally:
        fixture.close()


def test_fall_is_critical_and_outranks_every_other_reason() -> None:
    fixture, application, _sessions, _alerts = _operator_review_api()
    work_session_id = str(uuid4())
    risk = _alert(
        work_session_id,
        12,
        violation_type="person_in_risk_area",
        subject_key="risk_area:7",
        summary="Pessoa dentro da área de risco",
    )
    fall = _alert(
        work_session_id,
        12,
        violation_type="fall_detected",
        subject_key="fall:person",
        summary="Possível queda detectada",
        camera_id=None,
    )
    try:
        with (
            TestClient(application) as client,
            client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
        ):
            _next_state(ws, "GREEN")
            assert client.post("/operator/alerts", json=risk).status_code == 201
            _next_state(ws, "RED", "PERSON_IN_RISK_AREA")
            assert client.post("/operator/alerts", json=fall).status_code == 201
            assert _next_state(ws, "RED", "FALL_DETECTED")["active_conditions"] == 2
            assert client.post("/operator/alerts", json=_resolved(fall)).status_code == 201
            _next_state(ws, "RED", "PERSON_IN_RISK_AREA")
            assert client.post("/operator/alerts", json=_resolved(risk)).status_code == 201
            _next_state(ws, "GREEN")
            admin = {"Authorization": f"Bearer {_token(client)}"}
            listed = client.get("/admin/alerts", headers=admin).json()
            items = listed["items"] if isinstance(listed, dict) else listed
            assert "safety" in {item["category"] for item in items}
    finally:
        fixture.close()


def test_ended_or_replaced_session_resolves_its_orphaned_conditions() -> None:
    fixture = _api()
    application, sessions, *_ = next(fixture)
    _with_device(application)
    application.dependency_overrides[get_current_admin] = lambda: AdministratorPrincipal(
        account_id=1, name="Admin", username="admin", profile="administrador"
    )
    _seed_operation(sessions)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    first_session = str(uuid4())
    try:
        with (
            TestClient(application) as client,
            client.websocket_connect("/ws/devices/safety", headers=DEVICE_HEADERS) as ws,
        ):
            _next_state(ws, "GREEN")
            assert (
                client.post(
                    "/operator/alerts", json=_alert(first_session, 41), headers=headers
                ).status_code
                == 201
            )
            _next_state(ws, "RED")
            # The Operator crashed without resolving; a new session of the same operator starts.
            second_session = str(uuid4())
            second_started_at = datetime.now(UTC).isoformat()
            snapshot = _snapshot(
                second_session, second_started_at, {1: "collecting", 2: "collecting"}
            )
            assert (
                client.put("/operator/safety-state", json=snapshot, headers=headers).status_code
                == 200
            )
            _next_state(ws, "GREEN")

            # A session that ends with an active condition releases it as well.
            warning = _alert(second_session, 41, severity="warning")
            assert client.post("/operator/alerts", json=warning, headers=headers).status_code == 201
            _next_state(ws, "YELLOW")
            ended = _snapshot(second_session, second_started_at, {}) | {"session_status": "ended"}
            assert (
                client.put("/operator/safety-state", json=ended, headers=headers).status_code == 200
            )
            _next_state(ws, "GREEN")

        with sessions() as session:
            statuses = session.execute(select(PERSISTED_SAFETY_ALERTS.c.status)).scalars().all()
            assert statuses == ["nao_lido", "nao_lido"]
    finally:
        fixture.close()
