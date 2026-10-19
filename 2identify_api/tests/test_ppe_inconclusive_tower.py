"""Operator PPE conditions drive the device tower through the real HTTP and WebSocket API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from app.api.dependencies import get_current_admin
from app.models import PERSISTED_SAFETY_ALERTS
from app.services import AdministratorPrincipal
from tests.test_operator_alerts import _api

DEVICE_TOKEN = "tower-test-token-at-least-32-random-bytes"
_OPERATION_ID = 41
_CAMERA_ID = 5


def _seed_operation(sessions) -> None:
    """Create the operation catalog the safety snapshot is validated against."""

    now = datetime.now(UTC)
    with sessions.kw["bind"].begin() as connection:
        for statement in (
            "CREATE TABLE setores (id INTEGER PRIMARY KEY, nome VARCHAR(100), ativo BOOLEAN)",
            "CREATE TABLE cameras (id INTEGER PRIMARY KEY, nome VARCHAR(100), "
            "descricao VARCHAR(255), endereco VARCHAR(500), setor_id INTEGER, ativa BOOLEAN, "
            "criado_em DATETIME)",
            "CREATE TABLE epis (id INTEGER PRIMARY KEY, nome VARCHAR(100), codigo VARCHAR(50), "
            "descricao VARCHAR(500), ativo BOOLEAN)",
            "CREATE TABLE areas_risco (id INTEGER PRIMARY KEY, camera_id INTEGER, "
            "nome VARCHAR(120), geometria JSON, ativa BOOLEAN, criado_em DATETIME, "
            "atualizado_em DATETIME)",
            "CREATE TABLE operacoes (id INTEGER PRIMARY KEY, nome VARCHAR(150), "
            "descricao VARCHAR(500), area_risco_id INTEGER, ativa BOOLEAN, criado_em DATETIME, "
            "atualizado_em DATETIME)",
            "CREATE TABLE operacao_epis (operacao_id INTEGER, epi_id INTEGER, criado_em DATETIME, "
            "PRIMARY KEY (operacao_id, epi_id))",
        ):
            connection.execute(text(statement))
        connection.execute(text("INSERT INTO setores VALUES (1, 'Produção', 1)"))
        connection.execute(
            text("INSERT INTO cameras VALUES (:id, 'Linha A', NULL, 'rtsp://a', 1, 1, :now)"),
            {"id": _CAMERA_ID, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO epis VALUES (1, 'Capacete', 'CAP', NULL, 1), "
                "(2, 'Luvas', 'LUV', NULL, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO areas_risco VALUES (7, :camera, 'Linha', "
                '\'{"type": "polygon", "points": [[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]]}\', '
                "1, :now, :now)"
            ),
            {"camera": _CAMERA_ID, "now": now},
        )
        connection.execute(
            text("INSERT INTO operacoes VALUES (:id, 'Fresagem', NULL, 7, 1, :now, :now)"),
            {"id": _OPERATION_ID, "now": now},
        )
        connection.execute(
            text("INSERT INTO operacao_epis VALUES (:id, 1, :now), (:id, 2, :now)"),
            {"id": _OPERATION_ID, "now": now},
        )


def _alert(work_session_id: str, **fields) -> dict[str, object]:
    """Same JSON shape that OperatorApiClient.send_alert produces."""

    timestamp = datetime.now(UTC).isoformat()
    return {
        "event_id": str(uuid4()),
        "work_session_id": work_session_id,
        "operation_id": _OPERATION_ID,
        "camera_id": _CAMERA_ID,
        "risk_area_id": None,
        "status": "active",
        "resolved_at": None,
        "first_observed_at": timestamp,
        "raised_at": timestamp,
        **fields,
    }


def _inconclusive(work_session_id: str) -> dict[str, object]:
    return _alert(
        work_session_id,
        violation_type="monitoring_interrupted",
        subject_key="ppe_inconclusive:1",
        summary="Monitoramento de EPI inconclusivo: Capacete",
        severity="warning",
    )


def _absent(work_session_id: str) -> dict[str, object]:
    return _alert(
        work_session_id,
        violation_type="ppe_absent",
        subject_key="ppe:2",
        summary="EPI obrigatório ausente: Luvas",
        severity="warning",
    )


def _resolved(payload: dict[str, object]) -> dict[str, object]:
    return payload | {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}


def _snapshot(work_session_id: str, started_at: str, ppe: dict[int, str]) -> dict[str, object]:
    """Same JSON shape that OperatorApiClient.send_safety_state produces."""

    return {
        "work_session_id": work_session_id,
        "operation_id": _OPERATION_ID,
        "camera_id": _CAMERA_ID,
        "observed_at": datetime.now(UTC).isoformat(),
        "started_at": started_at,
        "session_status": "active",
        "ppe": [{"ppe_id": ppe_id, "state": state} for ppe_id, state in ppe.items()],
        # The Operator snapshot carries PPE conditions only; monitoring faults reach the
        # tower through the persisted alert lifecycle.
        "conditions": [],
    }


def _next_state(ws, expected: str, reason: str | None = None) -> dict[str, object]:
    # Heartbeats repeat the current state, so skip until the transition arrives.
    for _ in range(20):
        message = ws.receive_json()
        if message["state"] == expected and (reason is None or message["reason"] == reason):
            return message
    pytest.fail(f"{expected}/{reason} not delivered to the device")


def test_ppe_conditions_drive_the_tower_green_yellow_red_green_with_reasons() -> None:
    fixture = _api()
    application, sessions, _broker, *_ = next(fixture)
    application.state.settings = application.state.settings.model_copy(
        update={
            "safety_device_token": SecretStr(DEVICE_TOKEN),
            "realtime_heartbeat_interval_seconds": 0.1,
        }
    )
    application.dependency_overrides[get_current_admin] = lambda: AdministratorPrincipal(
        account_id=1, name="Admin", username="admin", profile="administrador"
    )
    _seed_operation(sessions)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    work_session_id = str(uuid4())
    started_at = datetime.now(UTC).isoformat()
    try:
        with (
            TestClient(application) as client,
            client.websocket_connect(
                "/ws/devices/safety", headers={"Authorization": f"Bearer {DEVICE_TOKEN}"}
            ) as ws,
        ):
            assert _next_state(ws, "GREEN")["active_conditions"] == 0

            def put(ppe: dict[int, str]) -> dict[str, object]:
                response = client.put(
                    "/operator/safety-state",
                    json=_snapshot(work_session_id, started_at, ppe),
                    headers=headers,
                )
                assert response.status_code == 200
                return response.json()

            def post(payload: dict[str, object]) -> None:
                response = client.post("/operator/alerts", json=payload, headers=headers)
                assert response.status_code == 201

            # Operation start: nothing confirmed yet, no condition.
            assert put({1: "collecting", 2: "collecting"})["state"] == "GREEN"
            active = client.get("/admin/active-operations").json()
            assert [item["operation_id"] for item in active] == [_OPERATION_ID]

            # Prolonged UNKNOWN for the helmet: MEDIUM monitoring condition → YELLOW.
            inconclusive = _inconclusive(work_session_id)
            post(inconclusive)
            message = _next_state(ws, "YELLOW")
            assert (message["reason"], message["active_conditions"]) == (
                "MONITORING_INTERRUPTED",
                1,
            )
            assert put({1: "unstable", 2: "confirmed"})["state"] == "YELLOW"

            # Gloves confirmed absent: the alert starts as a warning, then escalates.
            absent = _absent(work_session_id)
            post(absent)
            # Same level: the PPE reason outranks the monitoring reason.
            message = _next_state(ws, "YELLOW", "PPE_MISSING")
            assert message["active_conditions"] == 2
            post(absent | {"severity": "critical"})
            message = _next_state(ws, "RED")
            # The critical condition prevails over the simultaneous inconclusive one.
            assert (message["reason"], message["active_conditions"]) == ("PPE_MISSING", 2)
            assert put({1: "unstable", 2: "absent"})["state"] == "RED"

            # Gloves back on: only the inconclusive helmet remains.
            post(_resolved(absent | {"severity": "critical"}))
            message = _next_state(ws, "YELLOW", "MONITORING_INTERRUPTED")
            assert message["active_conditions"] == 1

            # Reliable helmet evidence returns: automatic resolution → GREEN.
            post(_resolved(inconclusive))
            message = _next_state(ws, "GREEN")
            assert (message["reason"], message["active_conditions"]) == (None, 0)
            assert put({1: "confirmed", 2: "confirmed"})["state"] == "GREEN"

            ended = _snapshot(work_session_id, started_at, {}) | {"session_status": "ended"}
            assert (
                client.put("/operator/safety-state", json=ended, headers=headers).json()["state"]
                == "GREEN"
            )
            assert client.get("/admin/active-operations").json() == []

        with sessions() as session:
            levels = session.execute(
                select(PERSISTED_SAFETY_ALERTS.c.nivel).order_by(PERSISTED_SAFETY_ALERTS.c.id)
            ).scalars()
            assert list(levels) == ["aviso", "critico"]
    finally:
        fixture.close()


def test_snapshot_alone_cannot_change_the_tower() -> None:
    fixture = _api()
    application, sessions, *_ = next(fixture)
    _seed_operation(sessions)
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    work_session_id = str(uuid4())
    started_at = datetime.now(UTC).isoformat()
    try:
        with TestClient(application) as client:
            snapshot = _snapshot(work_session_id, started_at, {1: "absent", 2: "unstable"})
            snapshot["conditions"] = [
                {
                    "condition_id": "ppe_absent:ppe:1",
                    "reason": "PPE_MISSING",
                    "level": "critical",
                    "first_observed_at": started_at,
                }
            ]
            response = client.put("/operator/safety-state", json=snapshot, headers=headers)
            assert response.status_code == 200
            # Only a persisted alert turns the tower; a volatile snapshot does not.
            assert response.json()["state"] == "GREEN"
    finally:
        fixture.close()
