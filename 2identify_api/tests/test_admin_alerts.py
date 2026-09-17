"""Administrative alert inbox and audited lifecycle tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import bcrypt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.main import create_app
from app.models import Base, SafetyAlertIngestion, Usuario
from tests.test_admin_api import LifecycleDatabase, make_settings


def _alert_api(
    *,
    operation_id: int = 12,
    seed_operation: bool = True,
    include_ingestion: bool = True,
) -> Iterator[tuple[FastAPI, sessionmaker[Session], Table]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    metadata = MetaData()
    sectors = Table(
        "setores",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(100), nullable=False),
    )
    employees = Table(
        "funcionarios",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(150), nullable=False),
        Column("matricula", String(50), nullable=False),
        Column("cargo", String(100)),
        Column("turno", String(50)),
        Column("setor_id", Integer),
    )
    cameras = Table(
        "cameras",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(100), nullable=False),
        Column("descricao", String(255)),
        Column("setor_id", Integer),
    )
    occurrences = Table(
        "ocorrencias",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("funcionario_id", Integer),
        Column("camera_id", Integer),
        Column("tipo", String(100), nullable=False),
        Column("descricao", Text),
        Column("confianca", Float),
        Column("imagem", String(500)),
        Column("video", String(500)),
        Column("detectado_em", DateTime(timezone=True), nullable=False),
    )
    alerts = Table(
        "alertas",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("ocorrencia_id", Integer, nullable=False, unique=True),
        Column("nivel", String(30), nullable=False),
        Column("status", String(30), nullable=False),
        Column("observacao", Text),
        Column("criado_em", DateTime(timezone=True), nullable=False),
        Column("recebido_em", DateTime(timezone=True)),
        Column("confirmado_em", DateTime(timezone=True)),
        Column("confirmado_por", Integer),
        Column("encerrado_em", DateTime(timezone=True)),
        Column("encerrado_por", Integer),
    )
    operations = Table(
        "operacoes",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(150), nullable=False),
    )
    metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = make_settings()
    application = create_app(settings=settings, database=LifecycleDatabase())

    def override_get_db() -> Iterator[Session]:
        with sessions() as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    now = datetime.now(UTC)
    with sessions.begin() as session:
        administrator = Usuario(
            nome="Administradora Segurança",
            username="admin",
            senha_hash=bcrypt.hashpw(b"senha-segura", bcrypt.gensalt()).decode(),
            perfil="administrador",
            ativo=True,
            criado_em=now,
            atualizado_em=now,
        )
        operator = Usuario(
            nome="Operador Ergonomia",
            username="operador",
            senha_hash=bcrypt.hashpw(b"senha-segura", bcrypt.gensalt()).decode(),
            perfil="operador",
            ativo=True,
            criado_em=now,
            atualizado_em=now,
        )
        session.add_all((administrator, operator))
        session.flush()
        session.execute(sectors.insert(), {"id": 3, "nome": "Montagem"})
        session.execute(
            employees.insert(),
            {
                "id": 4,
                "nome": "Funcionário Teste",
                "matricula": "MAT-004",
                "cargo": "Montador",
                "turno": "Manhã",
                "setor_id": 3,
            },
        )
        session.execute(
            cameras.insert(),
            {
                "id": 5,
                "nome": "Câmera Posto 5",
                "descricao": "Linha de montagem",
                "setor_id": 3,
            },
        )
        session.execute(
            occurrences.insert(),
            {
                "id": 10,
                "funcionario_id": 4,
                "camera_id": 5,
                "tipo": "ergonomic_risk",
                "descricao": "Tronco inclinado 52° em relação à vertical",
                "confianca": 0.94,
                "imagem": "evidencias/alerta-10.jpg",
                "video": None,
                "detectado_em": now,
            },
        )
        session.execute(
            alerts.insert(),
            {
                "id": 20,
                "ocorrencia_id": 10,
                "nivel": "critico",
                "status": "nao_lido",
                "observacao": "Triagem ergonômica automática",
                "criado_em": now,
                "recebido_em": now,
                "confirmado_em": None,
                "confirmado_por": None,
                "encerrado_em": None,
                "encerrado_por": None,
            },
        )
        if seed_operation:
            session.execute(operations.insert(), {"id": operation_id, "nome": "Soldagem"})
        if include_ingestion:
            session.add(
                SafetyAlertIngestion(
                    evento_id=uuid4(),
                    payload_hash="a" * 64,
                    alerta_id=20,
                    sessao_trabalho_id=uuid4(),
                    operador_usuario_id=operator.id,
                    operacao_id=operation_id,
                    area_risco_id=7,
                    violacao_tipo="ergonomic_risk",
                    assunto_chave="ergonomics:trunk_inclination",
                    recebido_em=now,
                )
            )
    application.state.test_admin_id = administrator.id
    yield application, sessions, alerts
    application.dependency_overrides.clear()
    engine.dispose()


def _token(client: TestClient) -> str:
    response = client.post(
        "/auth/admin/login",
        json={"username": "admin", "password": "senha-segura"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_alert_list_exposes_complete_ergonomic_occurrence() -> None:
    fixture = _alert_api()
    application, _sessions, _alerts = next(fixture)
    try:
        with TestClient(application) as client:
            token = _token(client)
            response = client.get(
                "/admin/alerts",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        alert = payload["items"][0]
        assert alert["category"] == "ergonomics"
        assert alert["level"] == "critical"
        assert alert["status"] == "nao_lido"
        assert alert["occurrence"]["employee"]["registration"] == "MAT-004"
        assert alert["occurrence"]["camera"]["name"] == "Câmera Posto 5"
        assert alert["occurrence"]["camera"]["sector"]["name"] == "Montagem"
        assert alert["operational_context"]["operator"]["name"] == "Operador Ergonomia"
        assert alert["operational_context"]["operation_id"] == 12
        assert alert["operational_context"]["operation_name"] == "Soldagem"
        assert response.headers["cache-control"] == "no-store"
    finally:
        fixture.close()


def test_synthetic_mobile_alert_flows_through_operator_and_admin_api() -> None:
    """Exercise the real HTTP contracts without writing to the restored database."""
    fixture = _alert_api()
    application, _sessions, _alerts = next(fixture)
    try:
        with TestClient(application) as client:
            operator_login = client.post(
                "/auth/login",
                json={"username": "operador", "password": "senha-segura"},
            )
            assert operator_login.status_code == 200
            now = datetime.now(UTC).isoformat()
            created = client.post(
                "/operator/alerts",
                headers={
                    "Authorization": f"Bearer {operator_login.json()['access_token']}"
                },
                json={
                    "event_id": str(uuid4()),
                    "work_session_id": str(uuid4()),
                    "operation_id": 12,
                    "camera_id": 5,
                    "risk_area_id": None,
                    "violation_type": "monitoring_interrupted",
                    "subject_key": "test:mobile_integration",
                    "summary": "TESTE DE INTEGRAÇÃO MOBILE 2IDENTIFY",
                    "severity": "warning",
                    "first_observed_at": now,
                    "raised_at": now,
                },
            )
            assert created.status_code == 201
            listed = client.get(
                "/admin/alerts?limit=100&offset=0",
                headers={"Authorization": f"Bearer {_token(client)}"},
            )
        assert listed.status_code == 200
        alert = next(
            item
            for item in listed.json()["items"]
            if item["id"] == created.json()["alert_id"]
        )
        assert alert["summary"] == "TESTE DE INTEGRAÇÃO MOBILE 2IDENTIFY"
        assert alert["level"] == "warning"
        assert alert["status"] == "nao_lido"
        assert alert["occurrence"]["camera"]["id"] == 5
        assert alert["occurrence"]["camera"]["name"] == "Câmera Posto 5"
        assert alert["created_at"]
    finally:
        fixture.close()


def test_unknown_logical_operation_keeps_alert_with_null_operation_name() -> None:
    fixture = _alert_api(operation_id=999, seed_operation=False)
    application, _sessions, _alerts = next(fixture)
    try:
        with TestClient(application) as client:
            response = client.get(
                "/admin/alerts",
                headers={"Authorization": f"Bearer {_token(client)}"},
            )

        assert response.status_code == 200
        context = response.json()["items"][0]["operational_context"]
        assert context["operation_id"] == 999
        assert context["operation_name"] is None
    finally:
        fixture.close()


def test_alert_without_ingestion_is_still_returned_without_operation() -> None:
    fixture = _alert_api(seed_operation=False, include_ingestion=False)
    application, _sessions, _alerts = next(fixture)
    try:
        with TestClient(application) as client:
            response = client.get(
                "/admin/alerts",
                headers={"Authorization": f"Bearer {_token(client)}"},
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["operational_context"] is None
    finally:
        fixture.close()


def test_alert_must_be_confirmed_before_occurrence_is_closed() -> None:
    fixture = _alert_api()
    application, _sessions, _alerts = next(fixture)
    try:
        with TestClient(application) as client:
            token = _token(client)
            response = client.patch(
                "/admin/alerts/20/close",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
        assert response.status_code == 409
        assert "confirme" in response.json()["detail"].lower()
    finally:
        fixture.close()


def test_confirmation_and_closure_are_audited_and_idempotent() -> None:
    fixture = _alert_api()
    application, sessions, alerts = next(fixture)
    try:
        with TestClient(application) as client:
            token = _token(client)
            headers = {"Authorization": f"Bearer {token}"}
            confirmed = client.patch("/admin/alerts/20/confirm", headers=headers, json={})
            closed = client.patch("/admin/alerts/20/close", headers=headers, json={})
            duplicate_close = client.patch(
                "/admin/alerts/20/close",
                headers=headers,
                json={},
            )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "lido"
        assert confirmed.json()["confirmed_by"]["name"] == "Administradora Segurança"
        assert closed.status_code == 200
        assert closed.json()["status"] == "encerrado"
        assert closed.json()["closed_by"]["id"] == application.state.test_admin_id
        assert duplicate_close.status_code == 200
        with sessions() as session:
            row = session.execute(select(alerts).where(alerts.c.id == 20)).mappings().one()
        assert row["confirmado_por"] == application.state.test_admin_id
        assert row["confirmado_em"] is not None
        assert row["encerrado_por"] == application.state.test_admin_id
        assert row["encerrado_em"] is not None
    finally:
        fixture.close()


def test_admin_alert_routes_require_an_administrator_bearer() -> None:
    fixture = _alert_api()
    application, _sessions, _alerts = next(fixture)
    try:
        with TestClient(application) as client:
            responses = (
                client.get("/admin/alerts"),
                client.get("/admin/alerts/20"),
                client.patch("/admin/alerts/20/confirm", json={}),
                client.patch("/admin/alerts/20/close", json={}),
            )
        assert all(response.status_code == 401 for response in responses)
    finally:
        fixture.close()
