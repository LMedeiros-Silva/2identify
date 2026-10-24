"""Public, read-only alert panel: sanitized data, no writes, change feed."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
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
    update,
)

from app.models import Base, SafetyAlertIngestion
from app.public_panel import create_public_app
from app.public_panel.config import PublicPanelSettings
from app.public_panel.feed import PublicAlertFeed
from app.public_panel.repository import PublicAlert

WEB_DIR = Path(__file__).resolve().parents[2] / "2identify_web"
CREATED = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)
PUBLIC_KEYS = {
    "id",
    "category",
    "severity",
    "title",
    "status",
    "condition",
    "camera",
    "sector",
    "operation",
    "created_at",
    "updated_at",
}


def _tables(metadata: MetaData) -> dict[str, Table]:
    return {
        "funcionarios": Table(
            "funcionarios",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("nome", String(150)),
            Column("matricula", String(50)),
        ),
        "setores": Table(
            "setores", metadata, Column("id", Integer, primary_key=True), Column("nome", String)
        ),
        "cameras": Table(
            "cameras",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("nome", String(100)),
            Column("descricao", String(255)),
            Column("setor_id", Integer),
        ),
        "operacoes": Table(
            "operacoes",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("nome", String(150)),
        ),
        "ocorrencias": Table(
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
        ),
        "alertas": Table(
            "alertas",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("ocorrencia_id", Integer, nullable=False),
            Column("nivel", String(30), nullable=False),
            Column("status", String(30), nullable=False),
            Column("observacao", Text),
            Column("criado_em", DateTime(timezone=True), nullable=False),
            Column("recebido_em", DateTime(timezone=True)),
            Column("confirmado_em", DateTime(timezone=True)),
            Column("confirmado_por", Integer),
            Column("encerrado_em", DateTime(timezone=True)),
            Column("encerrado_por", Integer),
        ),
    }


@pytest.fixture
def panel(tmp_path: Path) -> Iterator[tuple[TestClient, object, dict[str, Table]]]:
    url = f"sqlite+pysqlite:///{tmp_path / 'panel.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["usuarios"]])
    Base.metadata.create_all(engine, tables=[SafetyAlertIngestion.__table__])
    metadata = MetaData()
    tables = _tables(metadata)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            tables["funcionarios"].insert(),
            [{"id": 1, "nome": "Maria Souza", "matricula": "MAT-9981"}],
        )
        connection.execute(tables["setores"].insert(), [{"id": 1, "nome": "Linha A"}])
        connection.execute(
            tables["cameras"].insert(),
            [
                {
                    "id": 1,
                    "nome": "Câmera 2",
                    "descricao": "rtsp://user:segredo@10.0.0.2",
                    "setor_id": 1,
                }
            ],
        )
        connection.execute(tables["operacoes"].insert(), [{"id": 1, "nome": "Montagem"}])
        connection.execute(
            tables["ocorrencias"].insert(),
            [
                {
                    "id": 1,
                    "funcionario_id": 1,
                    "camera_id": 1,
                    "tipo": "FALL_DETECTED",
                    "descricao": "Queda detectada",
                    "confianca": 0.93,
                    "imagem": "evidencias/maria.jpg",
                    "detectado_em": CREATED,
                },
                {
                    "id": 2,
                    "funcionario_id": 1,
                    "camera_id": 1,
                    "tipo": "PPE_ABSENT",
                    "descricao": None,
                    "confianca": None,
                    "imagem": None,
                    "detectado_em": CREATED,
                },
            ],
        )
        connection.execute(
            tables["alertas"].insert(),
            [
                {
                    "id": 10,
                    "ocorrencia_id": 1,
                    "nivel": "critical",
                    "status": "nao_lido",
                    "observacao": "Nota interna do Admin",
                    "criado_em": CREATED,
                    "confirmado_em": None,
                    "confirmado_por": None,
                },
                {
                    "id": 11,
                    "ocorrencia_id": 2,
                    "nivel": "warning",
                    "status": "lido",
                    "observacao": None,
                    "criado_em": CREATED + timedelta(minutes=1),
                    "confirmado_em": CREATED + timedelta(minutes=2),
                    "confirmado_por": 7,
                },
            ],
        )
        connection.execute(
            SafetyAlertIngestion.__table__.insert(),
            [
                {
                    "evento_id": uuid4(),
                    "payload_hash": "0" * 64,
                    "alerta_id": 10,
                    "sessao_trabalho_id": uuid4(),
                    "operacao_id": 1,
                    "violacao_tipo": "fall_detected",
                    "assunto_chave": "fall:1",
                    "recebido_em": CREATED,
                }
            ],
        )
    settings = PublicPanelSettings(
        database_url=url,
        public_panel_web_dir=WEB_DIR,
        public_panel_poll_seconds=0.2,
        public_panel_url="https://painel.exemplo.com/",
    )
    with TestClient(create_public_app(settings)) as client:
        yield client, engine, tables
    engine.dispose()


def test_snapshot_exposes_only_sanitized_alert_fields(panel) -> None:
    client, _, _ = panel

    response = client.get("/api/public/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["source_online"] is True
    alerts = body["alerts"]
    assert [alert["id"] for alert in alerts] == [11, 10]
    assert all(set(alert) == PUBLIC_KEYS for alert in alerts)
    fall = alerts[1]
    assert fall["category"] == "fall"
    assert fall["severity"] == "critical"
    assert fall["title"] == "Queda detectada"
    assert fall["status"] == "novo"
    assert fall["condition"] == "ativa"
    assert (fall["camera"], fall["sector"], fall["operation"]) == (
        "Câmera 2",
        "Linha A",
        "Montagem",
    )
    ppe = alerts[0]
    assert ppe["title"] == "EPI obrigatório ausente"
    assert ppe["status"] == "confirmado"
    assert ppe["updated_at"] == "2026-10-24T14:02:00.000Z"
    raw = response.text
    for secret in ("Maria", "MAT-9981", "maria.jpg", "Nota interna", "segredo", "0.93"):
        assert secret not in raw


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/public/alerts", "/api/public/stream", "/", "/admin/alerts"])
def test_panel_rejects_every_write(panel, method: str, path: str) -> None:
    client, _, _ = panel

    response = client.request(method, path)

    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD"


@pytest.mark.parametrize(
    "path",
    [
        "/admin/alerts",
        "/auth/login",
        "/docs",
        "/openapi.json",
        "/package.json",
        "/tests/panel.test.mjs",
        "/..%2F2identify_api%2F.env",
    ],
)
def test_panel_serves_nothing_beyond_the_public_files(panel, path: str) -> None:
    client, _, _ = panel

    assert client.get(path).status_code == 404


def test_panel_page_is_served_with_strict_headers(panel) -> None:
    client, _, _ = panel

    response = client.get("/")

    assert response.status_code == 200
    assert "2Identify ao vivo" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/qr").status_code == 200
    assert client.get("/panel.js").headers["content-type"].startswith("text/javascript")


def test_config_and_qr_code(panel) -> None:
    client, _, _ = panel

    assert client.get("/api/public/config").json() == {
        "public_url": "https://painel.exemplo.com"
    }
    qr = client.get("/api/public/qr.svg", params={"url": "https://painel.exemplo.com"})
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/svg+xml")
    assert qr.text.startswith("<svg")
    assert 'xmlns="http://www.w3.org/2000/svg"' in qr.text
    rejected = client.get("/api/public/qr.svg", params={"url": "javascript:alert(1)"})
    assert rejected.status_code == 422


def test_status_changes_reach_the_snapshot(panel) -> None:
    client, engine, tables = panel
    with engine.begin() as connection:
        connection.execute(
            update(tables["alertas"])
            .where(tables["alertas"].c.id == 10)
            .values(status="encerrado", encerrado_em=CREATED + timedelta(minutes=5))
        )
        connection.execute(
            update(SafetyAlertIngestion.__table__)
            .where(SafetyAlertIngestion.__table__.c.alerta_id == 10)
            .values(condicao_resolvida_em=CREATED + timedelta(minutes=4))
        )

    asyncio.run(client.app.state.feed.poll_once())  # type: ignore[attr-defined]

    fall = next(a for a in client.get("/api/public/alerts").json()["alerts"] if a["id"] == 10)
    assert (fall["status"], fall["condition"]) == ("encerrado", "resolvida")
    assert fall["updated_at"] == "2026-10-24T14:05:00.000Z"


def _alert(alert_id: int, status: str = "novo") -> PublicAlert:
    moment = f"2026-10-24T14:{alert_id:02d}:00.000Z"
    return PublicAlert(
        id=alert_id,
        category="ppe",
        severity="warning",
        title="EPI obrigatório ausente",
        status=status,
        condition="ativa",
        camera=None,
        sector=None,
        operation=None,
        created_at=moment,
        updated_at=moment,
    )


def test_feed_broadcasts_only_changes_oldest_first() -> None:
    rows = [_alert(2), _alert(1)]
    feed = PublicAlertFeed(lambda: list(rows), interval_seconds=1, max_listeners=2)

    async def scenario() -> list[object]:
        await feed.poll_once()
        listener = feed.subscribe()
        await feed.poll_once()  # nothing changed: nothing sent
        rows[:] = [_alert(4), _alert(3), _alert(2, "confirmado")]
        await feed.poll_once()
        events = []
        while not listener.queue.empty():
            events.append(listener.queue.get_nowait())
        return events

    events = asyncio.run(scenario())

    assert len(events) == 1
    assert events[0].kind == "alerts"
    assert [alert["id"] for alert in events[0].data["alerts"]] == [2, 3, 4]
    assert events[0].data["removed"] == [1]


def test_feed_reports_source_outage_and_recovery() -> None:
    state = {"fail": False}

    def load() -> list[PublicAlert]:
        if state["fail"]:
            raise ConnectionError("database down")
        return [_alert(1)]

    feed = PublicAlertFeed(load, interval_seconds=1, max_listeners=2)

    async def scenario() -> list[object]:
        await feed.poll_once()
        listener = feed.subscribe()
        state["fail"] = True
        await feed.poll_once()
        assert feed.snapshot()["alerts"], "last known alerts stay visible"
        state["fail"] = False
        await feed.poll_once()
        return [listener.queue.get_nowait() for _ in range(listener.queue.qsize())]

    events = asyncio.run(scenario())

    assert [(event.kind, event.data) for event in events] == [
        ("status", {"source_online": False}),
        ("status", {"source_online": True}),
    ]


def test_feed_caps_listeners() -> None:
    from app.public_panel.feed import FeedCapacityError

    feed = PublicAlertFeed(list, interval_seconds=1, max_listeners=1)
    feed.subscribe()
    with pytest.raises(FeedCapacityError):
        feed.subscribe()
