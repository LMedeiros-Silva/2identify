"""Employee CRUD and additive central Face ID persistence without hardware."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.api.dependencies import get_current_admin
from app.api.routes.admin_employees import router
from app.core.database import get_db
from app.services.admin_authorization import AdministratorPrincipal


def _migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/f1b2c3d4e5f6_criar_templates_faciais_funcionarios.py"
    )
    spec = spec_from_file_location("face_template_migration", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _database(*, seed_existing: bool = False):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    sectors = Table(
        "setores", metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(100), nullable=False),
        Column("ativo", Boolean, nullable=False),
    )
    employees = Table(
        "funcionarios", metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(150), nullable=False),
        Column("matricula", String(50), nullable=False, unique=True),
        Column("cargo", String(100)),
        Column("turno", String(50)),
        Column("foto", String(500)),
        Column("ativo", Boolean, nullable=False),
        Column("setor_id", Integer, nullable=False),
        Column("criado_em", DateTime(timezone=True), nullable=False),
        Column("atualizado_em", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(sectors.insert(), [
            {"id": 1, "nome": "Usinagem", "ativo": True},
            {"id": 2, "nome": "Inativo", "ativo": False},
        ])
        if seed_existing:
            now = datetime(2026, 9, 17, tzinfo=UTC)
            connection.execute(
                employees.insert(),
                {"id": 7, "nome": "Ana", "matricula": "A7", "ativo": True,
                 "setor_id": 1, "criado_em": now, "atualizado_em": now},
            )
        migration = _migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    return engine, employees


def test_additive_migration_preserves_existing_employees() -> None:
    engine, employees = _database(seed_existing=True)
    with engine.begin() as connection:
        assert inspect(connection).has_table("funcionario_face_templates")
        assert connection.scalar(select(employees.c.nome).where(employees.c.id == 7)) == "Ana"
    migration = _migration()
    try:
        migration.downgrade()
    except RuntimeError:
        pass
    else:
        raise AssertionError("downgrade destrutivo deve permanecer bloqueado")
    engine.dispose()


def test_employee_registration_edit_sector_active_and_face_template() -> None:
    engine, _ = _database()
    sessions = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router)

    def session_override() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_current_admin] = lambda: AdministratorPrincipal(
        1, "Admin", "admin", "administrador"
    )
    draft = {
        "name": "João Ávila", "registration": "MAT-11", "role": "Operador",
        "shift": "Manhã", "sector_id": 1, "active": True,
    }
    with TestClient(app) as client:
        invalid = client.post("/admin/employees", json={"name": " ", "sector_id": 1})
        assert invalid.status_code == 422
        assert client.post("/admin/employees", json={**draft, "sector_id": 2}).status_code == 409
        created = client.post("/admin/employees", json=draft)
        assert created.status_code == 201
        employee_id = created.json()["id"]
        assert created.json()["sector_name"] == "Usinagem"
        assert client.post("/admin/employees", json=draft).status_code == 409
        listed = client.get("/admin/employees").json()
        assert listed["total"] == 1
        assert listed["items"][0]["name"] == "João Ávila"
        updated = client.put(
            f"/admin/employees/{employee_id}", json={**draft, "role": "Líder", "active": False}
        )
        assert updated.status_code == 200
        assert updated.json()["role"] == "Líder"
        assert updated.json()["active"] is False
        assert client.get(f"/admin/employees/{employee_id}/face-template").status_code == 404
        vector = [1.0] + [0.0] * 127
        enrolled = client.put(
            f"/admin/employees/{employee_id}/face-template",
            json={"model_id": "opencv_sface_2021dec", "embedding": vector},
        )
        assert enrolled.status_code == 200
        assert enrolled.json()["model_id"] == "opencv_sface_2021dec"
        assert "embedding" not in enrolled.json()
        assert client.get(f"/admin/employees/{employee_id}/face-template").status_code == 200
        assert client.put(
            f"/admin/employees/{employee_id}/face-template",
            json={"model_id": "opencv_sface_2021dec", "embedding": [2.0] + [0.0] * 127},
        ).status_code == 422
        assert client.get("/admin/employees/999").status_code == 404
    engine.dispose()
