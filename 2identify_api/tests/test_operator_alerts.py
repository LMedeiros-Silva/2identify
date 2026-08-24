"""End-to-end persistence and realtime publication for Operator alerts."""

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
    func,
    select,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.security import AccessTokenService
from app.main import create_app
from app.models import Base, SafetyAlertIngestion, Usuario
from app.realtime import InMemoryRealtimeEventBroker
from app.schemas.realtime import RealtimeEventEnvelope
from tests.test_authentication import LifecycleDatabase, make_settings


class RecordingBroker(InMemoryRealtimeEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[RealtimeEventEnvelope] = []

    async def publish(self, event: RealtimeEventEnvelope):  # type: ignore[no-untyped-def]
        self.published.append(event)
        return await super().publish(event)


def _api() -> Iterator[
    tuple[FastAPI, sessionmaker[Session], RecordingBroker, Table, Table]
]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    metadata = MetaData()
    occurrences = Table(
        "ocorrencias",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
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
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("ocorrencia_id", Integer, nullable=False, unique=True),
        Column("nivel", String(30), nullable=False),
        Column("status", String(30), nullable=False),
        Column("observacao", Text),
        Column("criado_em", DateTime(timezone=True), nullable=False),
        Column("recebido_em", DateTime(timezone=True)),
        Column("encerrado_em", DateTime(timezone=True)),
        Column("encerrado_por", Integer),
    )
    metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = make_settings()
    broker = RecordingBroker()
    application = create_app(
        settings=settings,
        database=LifecycleDatabase(),
        realtime_event_broker=broker,
    )

    def override_get_db() -> Iterator[Session]:
        with sessions() as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    now = datetime.now(UTC)
    with sessions.begin() as session:
        account = Usuario(
            nome="Operador Ergonomia",
            username="operador.ergonomia",
            senha_hash=bcrypt.hashpw(b"senha", bcrypt.gensalt()).decode(),
            perfil="operador",
            ativo=True,
            criado_em=now,
            atualizado_em=now,
        )
        session.add(account)
    token = AccessTokenService(settings).issue(
        subject=account.id,
        name=account.nome,
        profile="operador",
    )
    application.state.test_token = token
    yield application, sessions, broker, occurrences, alerts
    application.dependency_overrides.clear()
    engine.dispose()


def _payload() -> dict[str, object]:
    timestamp = datetime.now(UTC).isoformat()
    return {
        "event_id": str(uuid4()),
        "work_session_id": str(uuid4()),
        "operation_id": 12,
        "camera_id": None,
        "risk_area_id": 4,
        "violation_type": "ergonomic_risk",
        "subject_key": "ergonomics:trunk_inclination",
        "summary": "Risco ergonômico: tronco inclinado 52° em relação à vertical",
        "severity": "critical",
        "first_observed_at": timestamp,
        "raised_at": timestamp,
    }


def test_alert_is_persisted_once_and_published_after_commit() -> None:
    fixture = _api()
    application, sessions, broker, occurrences, alerts = next(fixture)
    payload = _payload()
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    try:
        with TestClient(application) as client:
            created = client.post("/operator/alerts", json=payload, headers=headers)
            duplicate = client.post("/operator/alerts", json=payload, headers=headers)
        assert created.status_code == 201
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(occurrences)) == 1
            assert session.scalar(select(func.count()).select_from(alerts)) == 1
            assert session.scalar(
                select(func.count()).select_from(SafetyAlertIngestion)
            ) == 1
        assert len(broker.published) == 1
        event = broker.published[0]
        assert event.event_type == "alert.created"
        assert event.payload.category == "ergonomics"  # type: ignore[union-attr]
    finally:
        fixture.close()


def test_risk_area_alert_persists_context_and_publishes_admin_event() -> None:
    fixture = _api()
    application, sessions, broker, occurrences, _alerts = next(fixture)
    payload = _payload()
    payload.update(
        {
            "camera_id": 3,
            "risk_area_id": 4,
            "violation_type": "person_in_risk_area",
            "subject_key": "risk_area:4",
            "summary": "Pessoa detectada na área de risco: Linha A",
        }
    )
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    try:
        with TestClient(application) as client:
            created = client.post("/operator/alerts", json=payload, headers=headers)

        assert created.status_code == 201
        with sessions() as session:
            occurrence = session.execute(select(occurrences)).mappings().one()
            ingestion = session.scalar(select(SafetyAlertIngestion))
        assert occurrence["tipo"] == "person_in_risk_area"
        assert occurrence["camera_id"] == 3
        assert ingestion is not None
        assert ingestion.area_risco_id == 4
        assert ingestion.violacao_tipo == "person_in_risk_area"
        assert len(broker.published) == 1
        event = broker.published[0]
        assert event.event_type == "alert.created"
        assert event.payload.category == "risk_area"  # type: ignore[union-attr]
        assert event.payload.camera_id == 3  # type: ignore[union-attr]
    finally:
        fixture.close()


def test_reused_event_id_with_changed_payload_is_rejected() -> None:
    fixture = _api()
    application, _sessions, _broker, _occurrences, _alerts = next(fixture)
    payload = _payload()
    headers = {"Authorization": f"Bearer {application.state.test_token}"}
    try:
        with TestClient(application) as client:
            assert client.post("/operator/alerts", json=payload, headers=headers).status_code == 201
            payload["summary"] = "Risco ergonômico diferente"
            conflict = client.post("/operator/alerts", json=payload, headers=headers)
        assert conflict.status_code == 409
    finally:
        fixture.close()


def test_alert_ingestion_requires_operator_bearer() -> None:
    fixture = _api()
    application, _sessions, _broker, _occurrences, _alerts = next(fixture)
    try:
        with TestClient(application) as client:
            response = client.post("/operator/alerts", json=_payload())
        assert response.status_code == 401
    finally:
        fixture.close()
