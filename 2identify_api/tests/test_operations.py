"""Operation configuration API, geometry and permission contract tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from secrets import token_urlsafe

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    text,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_admin, get_current_operator
from app.core.config import Settings
from app.core.database import get_db
from app.main import create_app
from app.services import AdministratorPrincipal, OperatorPrincipal

_CATALOG_TOKEN = "catalog-token-with-at-least-thirty-two-bytes"


class LifecycleDatabase:
    def check_connection(self) -> None:
        return None

    def dispose(self) -> None:
        return None


@pytest.fixture
def operations_api() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "cameras",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(100), nullable=False),
        Column("descricao", String(255)),
        Column("endereco", String(500), nullable=False),
        Column("setor_id", Integer, nullable=False),
        Column("ativa", Boolean, nullable=False),
        Column("criado_em", DateTime(timezone=True), nullable=False),
    )
    Table(
        "setores",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(100), nullable=False),
        Column("ativo", Boolean, nullable=False),
    )
    Table(
        "epis",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(100), nullable=False),
        Column("codigo", String(50)),
        Column("descricao", String(500)),
        Column("ativo", Boolean, nullable=False),
    )
    Table(
        "areas_risco",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("camera_id", Integer, nullable=False),
        Column("nome", String(120), nullable=False),
        Column("geometria", JSON, nullable=False),
        Column("ativa", Boolean, nullable=False),
        Column("criado_em", DateTime(timezone=True), nullable=False),
        Column("atualizado_em", DateTime(timezone=True), nullable=False),
    )
    Table(
        "operacoes",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("nome", String(150), nullable=False),
        Column("descricao", String(500)),
        Column("area_risco_id", Integer, nullable=False),
        Column("ativa", Boolean, nullable=False),
        Column("criado_em", DateTime(timezone=True), nullable=False),
        Column("atualizado_em", DateTime(timezone=True), nullable=False),
    )
    Table(
        "operacao_epis",
        metadata,
        Column("operacao_id", Integer, primary_key=True),
        Column("epi_id", Integer, primary_key=True),
        Column("criado_em", DateTime(timezone=True), nullable=False),
    )
    # The tower reads persisted alerts independently from the live PPE snapshot.
    Table(
        "ocorrencias",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tipo", String(100)),
    )
    Table(
        "alertas",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("ocorrencia_id", Integer),
        Column("nivel", String(30)),
        Column("status", String(30)),
        Column("criado_em", DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with engine.begin() as connection:
        now = datetime.now(UTC)
        connection.execute(
            metadata.tables["setores"].insert(),
            [
                {"id": 1, "nome": "Produção", "ativo": True},
                {"id": 2, "nome": "Inativo", "ativo": False},
            ],
        )
        connection.execute(
            metadata.tables["cameras"].insert(),
            [
                {
                    "id": 5,
                    "nome": "Câmera Linha A",
                    "descricao": "Visão geral",
                    "endereco": "rtsp://camera.local/stream",
                    "setor_id": 1,
                    "ativa": True,
                    "criado_em": now,
                },
                {
                    "id": 6,
                    "nome": "Desativada",
                    "descricao": None,
                    "endereco": "0",
                    "setor_id": 1,
                    "ativa": False,
                    "criado_em": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["epis"].insert(),
            [
                {"id": 1, "nome": "Capacete", "codigo": "CAP", "ativo": True},
                {"id": 2, "nome": "Luvas", "codigo": "LUV", "ativo": True},
            ],
        )

    settings = Settings(
        database_url="postgresql+psycopg2://test:test@localhost/test",
        app_env="testing",
        auth_token_secret="test-secret-with-at-least-thirty-two-bytes",
        operator_catalog_token=_CATALOG_TOKEN,
        _env_file=None,
    )
    app = create_app(settings=settings, database=LifecycleDatabase())

    def override_db() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_admin] = lambda: AdministratorPrincipal(
        account_id=1, name="Admin", username="admin", profile="administrador"
    )
    app.dependency_overrides[get_current_operator] = lambda: OperatorPrincipal(
        account_id=2, name="Operador", profile="operador"
    )
    with TestClient(app) as client:
        yield client, sessions
    app.dependency_overrides.clear()
    engine.dispose()


def test_admin_creates_area_and_operation_operator_reads_same_polygon(operations_api) -> None:
    client, _sessions = operations_api
    catalog = client.get("/admin/operations/catalog")
    assert catalog.status_code == 200
    assert [item["id"] for item in catalog.json()["cameras"]] == [5]
    assert catalog.json()["sectors"] == [{"id": 1, "name": "Produção"}]

    geometry = {
        "type": "polygon",
        "points": [[0.18, 0.42], [0.65, 0.38], [0.76, 0.88], [0.12, 0.91]],
    }
    created_area = client.post(
        "/admin/risk-areas",
        json={"camera_id": 5, "name": "Linha A", "geometry": geometry},
    )
    assert created_area.status_code == 201
    area = created_area.json()
    assert area["geometry"] == geometry

    created_operation = client.post(
        "/admin/operations",
        json={
            "name": "Soldagem",
            "description": "Solda controlada",
            "epi_ids": [1, 2],
            "risk_area_id": area["id"],
        },
    )
    assert created_operation.status_code == 201
    assert [ppe["name"] for ppe in created_operation.json()["required_ppe"]] == [
        "Capacete",
        "Luvas",
    ]

    operator_view = client.get("/operator/operations")
    assert operator_view.status_code == 200
    assert operator_view.json()[0]["risk_area"]["geometry"] == geometry

    face_id_view = client.get(
        "/operator/operations/catalog",
        headers={"Authorization": f"Bearer {_CATALOG_TOKEN}"},
    )
    assert face_id_view.status_code == 200
    assert face_id_view.json() == operator_view.json()


def test_operator_camera_catalog_lists_active_sector_sources_without_usb_index(
    operations_api,
) -> None:
    client, _sessions = operations_api
    area = client.post(
        "/admin/risk-areas",
        json={
            "camera_id": 5,
            "name": "Linha multi",
            "geometry": {
                "type": "polygon",
                "points": [[0.1, 0.1], [0.8, 0.1], [0.5, 0.8]],
            },
        },
    ).json()
    operation = client.post(
        "/admin/operations",
        json={"name": "Monitoramento multi", "epi_ids": [1], "risk_area_id": area["id"]},
    ).json()
    for name, source in (
        ("Rede B", "rtsp://camera-b.local/live"),
        ("Rede C", "https://camera-c.local/mjpeg"),
        ("USB A", "0"),
        ("USB B", "1"),
    ):
        created = client.post(
            "/admin/cameras",
            json={"name": name, "stream_source": source, "sector_id": 1},
        )
        assert created.status_code == 201
    path = f"/operator/operations/{operation['id']}/cameras"
    response = client.get(path)
    assert response.status_code == 200
    cameras = response.json()
    assert len(cameras) == 5
    assert {item["sector_id"] for item in cameras} == {1}
    assert {item["source_type"] for item in cameras} == {"ip", "usb"}
    assert all(item["source_hint"] is None for item in cameras if item["source_type"] == "usb")
    assert client.get(
        f"/operator/operations/catalog/{operation['id']}/cameras",
        headers={"Authorization": f"Bearer {_CATALOG_TOKEN}"},
    ).json() == cameras


def test_operator_publishes_active_ppe_snapshot_for_admin(operations_api) -> None:
    client, _sessions = operations_api
    area = client.post(
        "/admin/risk-areas",
        json={
            "camera_id": 5,
            "name": "Linha monitorada",
            "geometry": {
                "type": "polygon",
                "points": [[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]],
            },
        },
    ).json()
    operation = client.post(
        "/admin/operations",
        json={
            "name": "Montagem monitorada",
            "description": None,
            "epi_ids": [1, 2],
            "risk_area_id": area["id"],
        },
    ).json()
    started_at = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    base_payload = {
        "work_session_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "operation_id": operation["id"],
        "camera_id": 5,
        "started_at": started_at.isoformat(),
        "observed_at": started_at.isoformat(),
        "session_status": "active",
        "ppe": [
            {"ppe_id": 1, "state": "confirmed"},
            {"ppe_id": 2, "state": "absent"},
        ],
        "conditions": [],
    }

    published = client.put("/operator/safety-state", json=base_payload)
    assert published.status_code == 200
    active = client.get("/admin/active-operations")
    assert active.status_code == 200
    assert active.json()[0]["operator_id"] == 2
    assert active.json()[0]["operator_name"] == "Operador"
    assert active.json()[0]["operation_name"] == "Montagem monitorada"
    assert active.json()[0]["overall_status"] == "non_compliant"

    ended_payload = {
        **base_payload,
        "session_status": "ended",
        "ppe": [],
    }
    ended = client.put("/operator/safety-state", json=ended_payload)
    assert ended.status_code == 200
    assert client.get("/admin/active-operations").json() == []


def test_operator_catalog_rejects_missing_or_invalid_device_token(operations_api) -> None:
    client, _sessions = operations_api

    missing = client.get("/operator/operations/catalog")
    invalid = client.get(
        "/operator/operations/catalog",
        headers={"Authorization": "Bearer invalid-catalog-token"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["cache-control"] == "no-store"


def test_admin_registers_camera_through_api_and_catalog_lists_it(operations_api) -> None:
    client, _sessions = operations_api
    created = client.post(
        "/admin/cameras",
        json={
            "name": "Webcam USB",
            "description": "Câmera de teste",
            "stream_source": "0",
            "sector_id": 1,
        },
    )

    assert created.status_code == 201
    assert created.json()["name"] == "Webcam USB"
    assert created.json()["stream_source"] == "0"
    catalog = client.get("/admin/operations/catalog").json()
    assert created.json()["id"] in [item["id"] for item in catalog["cameras"]]

    duplicate = client.post(
        "/admin/cameras",
        json={
            "name": "webcam usb",
            "description": None,
            "stream_source": "1",
            "sector_id": 1,
        },
    )
    assert duplicate.status_code == 409


def test_admin_can_list_edit_deactivate_and_move_sector_cameras(operations_api) -> None:
    client, sessions = operations_api
    with sessions.begin() as session:
        session.execute(
            text("INSERT INTO setores (id, nome, ativo) VALUES (3, 'Manutenção', true)")
        )

    listed = client.get("/admin/cameras")
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {5, 6}
    assert next(item for item in listed.json() if item["id"] == 6)["active"] is False

    updated = client.put(
        "/admin/cameras/5",
        json={
            "name": "Fresa revisada",
            "description": "Câmera deslocada",
            "stream_source": "rtsp://camera.local/stream",
            "sector_id": 3,
            "active": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["sector_id"] == 3
    assert updated.json()["active"] is False
    assert updated.json()["name"] == "Fresa revisada"
    assert client.get("/admin/operations/catalog").json()["cameras"] == []
    assert client.get("/admin/cameras?sector_id=3").json() == [updated.json()]

    reactivated = client.put(
        "/admin/cameras/5",
        json={
            "name": "Fresa revisada",
            "description": "Câmera deslocada",
            "stream_source": "rtsp://camera.local/stream",
            "sector_id": 3,
            "active": True,
        },
    )
    assert reactivated.status_code == 200
    assert [item["id"] for item in client.get("/admin/operations/catalog").json()["cameras"]] == [5]


def test_admin_camera_update_rejects_inactive_sector_and_duplicate_name(operations_api) -> None:
    client, _sessions = operations_api
    assert client.put(
        "/admin/cameras/5",
        json={"name": "Linha", "stream_source": "0", "sector_id": 2},
    ).status_code == 404
    assert client.put(
        "/admin/cameras/5",
        json={"name": "Desativada", "stream_source": "0", "sector_id": 1},
    ).status_code == 409
    assert client.put(
        "/admin/cameras/999",
        json={"name": "Ausente", "stream_source": "0", "sector_id": 1},
    ).status_code == 404


def test_admin_camera_edit_does_not_erase_hidden_legacy_credentials(operations_api) -> None:
    client, sessions = operations_api
    legacy_source = "rtsp://" + "test-user:" + token_urlsafe(12) + "@camera.local/stream?channel=1"
    with sessions.begin() as session:
        session.execute(
            text("UPDATE cameras SET endereco=:source WHERE id=5"),
            {"source": legacy_source},
        )
    camera = next(item for item in client.get("/admin/cameras").json() if item["id"] == 5)
    assert camera["stream_source"] == "rtsp://camera.local/stream"
    updated = client.put(
        "/admin/cameras/5",
        json={
            "name": "Renomeada", "stream_source": camera["stream_source"],
            "sector_id": 1, "active": False,
        },
    )
    assert updated.status_code == 200
    with sessions() as session:
        assert session.scalar(text("SELECT endereco FROM cameras WHERE id=5")) == legacy_source


def test_camera_registration_rejects_source_query_configuration(operations_api) -> None:
    client, _sessions = operations_api
    response = client.post(
        "/admin/cameras",
        json={
            "name": "Câmera IP",
            "stream_source": "rtsp://camera.local/live?option",
            "sector_id": 1,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "points",
    [
        [[0.1, 0.1], [0.5, 0.5]],
        [[0.1, 0.1], [1.2, 0.1], [0.5, 0.8]],
        [[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]],
        [[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]],
    ],
)
def test_invalid_polygon_is_rejected_before_persistence(operations_api, points) -> None:
    client, _sessions = operations_api
    response = client.post(
        "/admin/risk-areas",
        json={
            "camera_id": 5,
            "name": "Inválida",
            "geometry": {"type": "polygon", "points": points},
        },
    )
    assert response.status_code == 422


def test_existing_risk_area_can_be_loaded_and_updated(operations_api) -> None:
    client, _sessions = operations_api
    created = client.post(
        "/admin/risk-areas",
        json={
            "camera_id": 5,
            "name": "Original",
            "geometry": {
                "type": "polygon",
                "points": [[0.1, 0.1], [0.8, 0.1], [0.4, 0.8]],
            },
        },
    ).json()
    updated = client.put(
        f"/admin/risk-areas/{created['id']}",
        json={
            "camera_id": 5,
            "name": "Editada",
            "geometry": {
                "type": "polygon",
                "points": [[0.2, 0.2], [0.9, 0.2], [0.5, 0.9]],
            },
        },
    )
    listed = client.get("/admin/risk-areas?camera_id=5")
    assert updated.status_code == 200
    assert listed.json()[0]["name"] == "Editada"
    assert listed.json()[0]["geometry"]["points"][0] == [0.2, 0.2]
