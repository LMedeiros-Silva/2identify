"""Face ID end to end: Admin template -> station login -> employee session -> alert -> tower."""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Iterator
from datetime import UTC, datetime
from math import sqrt
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from app.core.security import AccessTokenService
from app.models import SafetyAlertIngestion
from tests.test_operator_alerts import _api, make_settings
from tests.test_ppe_inconclusive_tower import _alert, _seed_operation, _snapshot

STATION_TOKEN = "station-test-token-with-at-least-32-random-bytes"
STATION = {"Authorization": f"Bearer {STATION_TOKEN}"}
DEVICE_TOKEN = "tower-test-token-at-least-32-random-bytes"
DEVICE = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
MODEL_ID = "opencv_sface_2021dec"
_RNG = random.Random(20261022)
Vector = list[float]


def _unit(vector: Vector) -> Vector:
    norm = sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


def _template() -> Vector:
    return _unit([_RNG.gauss(0.0, 1.0) for _ in range(128)])


def _near(template: Vector, noise: float) -> Vector:
    jitter = _template()
    return _unit([value + delta * noise for value, delta in zip(template, jitter, strict=True)])


def _probes(template: Vector, count: int = 3, noise: float = 0.35) -> list[Vector]:
    """Successive frames of the same face: close to the template, never identical."""

    return [_near(template, noise) for _ in range(count)]


ANA = _template()
BRUNO = _template()
CARLA_INACTIVE = _template()


def _seed_employees(sessions) -> None:
    now = datetime.now(UTC)
    with sessions.kw["bind"].begin() as connection:
        # The Admin review columns the alert fixture of test_operator_alerts leaves out.
        connection.execute(text("ALTER TABLE alertas ADD COLUMN confirmado_em DATETIME"))
        connection.execute(text("ALTER TABLE alertas ADD COLUMN confirmado_por INTEGER"))
        connection.execute(
            text(
                "CREATE TABLE funcionarios (id INTEGER PRIMARY KEY, nome VARCHAR(150), "
                "matricula VARCHAR(50), cargo VARCHAR(100), turno VARCHAR(50), "
                "foto VARCHAR(500), ativo BOOLEAN, setor_id INTEGER, criado_em DATETIME, "
                "atualizado_em DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE funcionario_face_templates (funcionario_id INTEGER PRIMARY KEY, "
                "model_id VARCHAR(80), embedding JSON, criado_em DATETIME, "
                "atualizado_em DATETIME)"
            )
        )
        for employee_id, name, active, template in (
            (21, "Ana Souza", True, ANA),
            (22, "Bruno Lima", True, BRUNO),
            (23, "Carla Dias", False, CARLA_INACTIVE),
            (24, "Davi Sem Rosto", True, None),
        ):
            connection.execute(
                text(
                    "INSERT INTO funcionarios VALUES (:id, :name, :registration, 'Operador', "
                    "'A', NULL, :active, 1, :now, :now)"
                ),
                {
                    "id": employee_id,
                    "name": name,
                    "registration": f"M{employee_id}",
                    "active": active,
                    "now": now,
                },
            )
            if template is not None:
                connection.execute(
                    text(
                        "INSERT INTO funcionario_face_templates "
                        "VALUES (:id, :model, :embedding, :now, :now)"
                    ),
                    {
                        "id": employee_id,
                        "model": MODEL_ID,
                        "embedding": json.dumps(template),
                        "now": now,
                    },
                )


@pytest.fixture
def face_api() -> Iterator[tuple[object, object, str]]:
    fixture = _api()
    application, sessions, *_ = next(fixture)
    application.state.settings = application.state.settings.model_copy(
        update={
            "operator_station_token": SecretStr(STATION_TOKEN),
            "safety_device_token": SecretStr(DEVICE_TOKEN),
            "realtime_heartbeat_interval_seconds": 0.05,
        }
    )
    _seed_operation(sessions)
    _seed_employees(sessions)
    try:
        yield application, sessions, application.state.test_token
    finally:
        fixture.close()


def _face_login(client, probes, headers=STATION, model_id=MODEL_ID):
    return client.post(
        "/auth/face",
        json={"model_id": model_id, "probes": probes},
        headers=headers,
    )


def test_registered_face_receives_an_employee_session_from_the_api(face_api) -> None:
    application, _sessions, _password_token = face_api
    with TestClient(application) as client:
        response = _face_login(client, _probes(ANA))
    assert response.status_code == 200
    body = response.json()
    assert body["operator"] == {
        "id": 21,
        "name": "Ana Souza",
        "profile": "funcionario",
        "profile_photo_reference": None,
    }
    assert body["token_type"] == "bearer"
    assert response.headers["cache-control"] == "no-store"
    claims = AccessTokenService(make_settings()).verify(body["access_token"])
    assert (claims.subject, claims.subject_type) == (21, "funcionario")


def test_face_id_session_reaches_admin_alert_and_safety_tower(face_api) -> None:
    """Face ID -> API session -> monitoring snapshot -> Admin alert -> ESP32 RED -> GREEN."""

    application, sessions, _password_token = face_api
    work_session_id, started_at = str(uuid4()), datetime.now(UTC).isoformat()
    with TestClient(application) as client:
        token = _face_login(client, _probes(ANA)).json()["access_token"]
        operator = {"Authorization": f"Bearer {token}"}
        snapshot = _snapshot(work_session_id, started_at, {1: "confirmed", 2: "confirmed"})
        assert (
            client.put("/operator/safety-state", json=snapshot, headers=operator).status_code == 200
        )
        with client.websocket_connect("/ws/devices/safety", headers=DEVICE) as ws:
            assert ws.receive_json()["state"] == "GREEN"
            fall = _alert(
                work_session_id,
                violation_type="fall_detected",
                subject_key="fall:5",
                summary="Queda detectada",
                severity="critical",
            )
            assert client.post("/operator/alerts", json=fall, headers=operator).status_code == 201
            for _ in range(60):
                if ws.receive_json()["state"] == "RED":
                    break
            else:
                pytest.fail("tower never turned RED for the Face ID session")
            ended = snapshot | {"session_status": "ended", "ppe": []}
            assert (
                client.put("/operator/safety-state", json=ended, headers=operator).status_code
                == 200
            )
            for _ in range(60):
                if ws.receive_json()["state"] == "GREEN":
                    break
            else:
                pytest.fail("tower stayed RED after the Face ID session ended")

        admin_token = _admin_token(sessions)
        alerts = client.get(
            "/admin/alerts", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
    employee = alerts["items"][0]["occurrence"]["employee"]
    # The Admin sees who was monitored: the employee recognized by Face ID.
    assert (employee["id"], employee["name"]) == (21, "Ana Souza")
    with sessions() as session:
        ingestion = session.scalars(select(SafetyAlertIngestion)).one()
        assert ingestion.operador_usuario_id is None
        assert ingestion.condicao_resolvida_em is not None


def _admin_token(sessions) -> str:
    import bcrypt

    from app.models import Usuario

    now = datetime.now(UTC)
    with sessions.begin() as session:
        admin = Usuario(
            nome="Admin",
            username="admin.face",
            senha_hash=bcrypt.hashpw(b"senha", bcrypt.gensalt()).decode(),
            perfil="administrador",
            ativo=True,
            criado_em=now,
            atualizado_em=now,
        )
        session.add(admin)
    settings = make_settings()
    return AccessTokenService(settings, audience=settings.auth_admin_token_audience).issue(
        subject=admin.id, name="Admin", profile="administrador"
    )


@pytest.mark.parametrize(
    ("headers", "configured", "expected"),
    [
        ({}, True, 403),
        ({"Authorization": "Bearer wrong-station-token-with-32-bytes-or-more"}, True, 403),
        (STATION, False, 503),
    ],
)
def test_station_must_authenticate_before_any_face_is_matched(
    face_api, headers, configured, expected
) -> None:
    application, _sessions, password_token = face_api
    if not configured:
        application.state.settings = application.state.settings.model_copy(
            update={"operator_station_token": None}
        )
    with TestClient(application) as client:
        assert _face_login(client, _probes(ANA), headers=headers).status_code == expected
        # An operator bearer is not a station credential either.
        operator = {"Authorization": f"Bearer {password_token}"}
        assert _face_login(client, _probes(ANA), headers=operator).status_code in {403, 503}


@pytest.mark.parametrize(
    "probes",
    [
        pytest.param(_probes(_template()), id="unknown-face"),
        pytest.param(_probes(CARLA_INACTIVE), id="inactive-employee"),
        pytest.param(_probes(ANA, 2) + _probes(BRUNO, 1), id="frames-of-two-people"),
        pytest.param([_probes(ANA, 1)[0]] * 3, id="replayed-identical-frame"),
    ],
)
def test_face_without_a_unique_authorized_employee_is_rejected(face_api, probes) -> None:
    application, *_ = face_api
    with TestClient(application) as client:
        response = _face_login(client, probes)
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_ambiguous_match_between_two_employees_is_rejected(face_api) -> None:
    application, sessions, _token = face_api
    twin = _near(ANA, 0.05)
    with sessions.kw["bind"].begin() as connection:
        connection.execute(
            text("UPDATE funcionario_face_templates SET embedding = :e WHERE funcionario_id = 22"),
            {"e": json.dumps(twin)},
        )
    with TestClient(application) as client:
        assert _face_login(client, _probes(ANA)).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"model_id": MODEL_ID, "probes": _probes(ANA, 1)},
        {"model_id": MODEL_ID, "probes": [[0.5] * 128] * 3},
        {"model_id": MODEL_ID, "probes": [[1.0] + [0.0] * 126] * 3},
        {"model_id": MODEL_ID, "probes": _probes(ANA), "employee_id": 21},
    ],
    ids=["single-frame", "not-normalized", "wrong-dimension", "client-chosen-employee"],
)
def test_malformed_face_request_is_refused_without_echoing_the_biometrics(face_api, body) -> None:
    application, *_ = face_api
    with TestClient(application) as client:
        response = client.post("/auth/face", json=body, headers=STATION)
    assert response.status_code == 422
    assert "0.5" not in response.text and '"input"' not in response.text


def test_other_model_templates_are_never_compared(face_api) -> None:
    application, *_ = face_api
    with TestClient(application) as client:
        assert _face_login(client, _probes(ANA), model_id="other_model").status_code == 401


def test_employee_token_stops_working_when_the_employee_is_deactivated(face_api) -> None:
    application, sessions, _token = face_api
    with TestClient(application) as client:
        token = _face_login(client, _probes(ANA)).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/operator/operations", headers=headers).status_code == 200
        with sessions.kw["bind"].begin() as connection:
            connection.execute(text("UPDATE funcionarios SET ativo = 0 WHERE id = 21"))
        assert client.get("/operator/operations", headers=headers).status_code == 401


def test_employee_token_is_not_an_admin_or_password_account_token(face_api) -> None:
    application, sessions, _token = face_api
    settings = make_settings()
    # Same subject number as a password account, but typed as an employee.
    forged_admin = AccessTokenService(settings, audience=settings.auth_admin_token_audience).issue(
        subject=1, name="Ana Souza", profile="administrador", subject_type="funcionario"
    )
    as_account = AccessTokenService(settings).issue(
        subject=21, name="Ana Souza", profile="funcionario"
    )
    with TestClient(application) as client:
        employee = _face_login(client, _probes(ANA)).json()["access_token"]
        assert (
            client.get("/admin/me", headers={"Authorization": f"Bearer {employee}"}).status_code
            == 401
        )
        assert (
            client.get("/admin/me", headers={"Authorization": f"Bearer {forged_admin}"}).status_code
            == 401
        )
        assert (
            client.get(
                "/operator/operations", headers={"Authorization": f"Bearer {as_account}"}
            ).status_code
            == 401
        )


def test_employee_cannot_resolve_an_alert_of_another_session_owner(face_api) -> None:
    application, _sessions, password_token = face_api
    work_session_id = str(uuid4())
    payload = _alert(
        work_session_id,
        violation_type="fall_detected",
        subject_key="fall:5",
        summary="Queda detectada",
        severity="critical",
    )
    with TestClient(application) as client:
        password = {"Authorization": f"Bearer {password_token}"}
        assert client.post("/operator/alerts", json=payload, headers=password).status_code == 201
        token = _face_login(client, _probes(ANA)).json()["access_token"]
        resolved = payload | {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
        response = client.post(
            "/operator/alerts", json=resolved, headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 409


def test_face_login_never_logs_embeddings_or_tokens(face_api, caplog) -> None:
    application, *_ = face_api
    probes = _probes(ANA)
    caplog.set_level(logging.DEBUG)
    with TestClient(application) as client:
        token = _face_login(client, probes).json()["access_token"]
        _face_login(client, _probes(_template()))
    logged = caplog.text + " ".join(str(record.__dict__) for record in caplog.records)
    assert token not in logged
    assert f"{probes[0][0]:.6f}"[:8] not in logged
    assert repr(probes[0][0]) not in logged
    assert "face_authentication_succeeded" in caplog.text
