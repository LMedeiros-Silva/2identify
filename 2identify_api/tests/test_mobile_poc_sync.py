"""Integration tests for selective, idempotent mobile PoC synchronization."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.mobile_poc.sync import (
    SYNC_TABLE_ORDER,
    SynchronizationError,
    SynchronizationReport,
    TableSyncResult,
    synchronize_engines,
)
from scripts.sync_mobile_poc_to_supabase import format_sync_report


def _schema(*, reject_employee: bool = False, include_password_hash: bool = True) -> MetaData:
    metadata = MetaData()
    users = Table(
        "usuarios",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(150), nullable=False),
        Column("username", String(100), nullable=False, unique=True),
        *(
            (Column("senha_hash", String(255), nullable=False),)
            if include_password_hash
            else ()
        ),
        Column("perfil", String(50), nullable=False),
        Column("ativo", Boolean, nullable=False),
    )
    sectors = Table("setores", metadata, Column("id", Integer, primary_key=True))
    cameras = Table(
        "cameras",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("setor_id", ForeignKey("setores.id"), nullable=False),
    )
    employees = Table(
        "funcionarios",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(150), nullable=False),
        Column("setor_id", ForeignKey("setores.id"), nullable=False),
        *(
            (CheckConstraint("nome != 'rejeitar'", name="ck_reject_employee"),)
            if reject_employee
            else ()
        ),
    )
    occurrences = Table(
        "ocorrencias",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("funcionario_id", ForeignKey("funcionarios.id")),
        Column("camera_id", ForeignKey("cameras.id")),
    )
    risk_areas = Table(
        "areas_risco",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("camera_id", ForeignKey("cameras.id"), nullable=False),
    )
    operations = Table(
        "operacoes",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("nome", String(150), nullable=False),
        Column("area_risco_id", ForeignKey("areas_risco.id"), nullable=False),
    )
    alerts = Table(
        "alertas",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("ocorrencia_id", ForeignKey("ocorrencias.id"), nullable=False, unique=True),
    )
    Table(
        "alertas_ingestao",
        metadata,
        Column("evento_id", String(36), primary_key=True),
        Column("alerta_id", ForeignKey("alertas.id"), nullable=False, unique=True),
        Column("operador_usuario_id", ForeignKey("usuarios.id")),
        Column("operacao_id", Integer, nullable=False),
    )
    assert all(
        item is not None
        for item in (
            users,
            sectors,
            cameras,
            employees,
            occurrences,
            risk_areas,
            operations,
            alerts,
        )
    )
    return metadata


def _engine(metadata: MetaData) -> Engine:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def _seed_local(engine: Engine, *, employee_name: str = "Operador Teste") -> None:
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["usuarios"].insert(),
            {
                "id": 7,
                "nome": "Admin Teste",
                "username": "admin",
                "senha_hash": "$2b$12$hash-preservado",
                "perfil": "administrador",
                "ativo": True,
            },
        )
        connection.execute(metadata.tables["setores"].insert(), {"id": 1})
        connection.execute(
            metadata.tables["cameras"].insert(), {"id": 2, "setor_id": 1}
        )
        connection.execute(
            metadata.tables["funcionarios"].insert(),
            {"id": 3, "nome": employee_name, "setor_id": 1},
        )
        connection.execute(
            metadata.tables["ocorrencias"].insert(),
            {"id": 4, "funcionario_id": 3, "camera_id": 2},
        )
        connection.execute(
            metadata.tables["areas_risco"].insert(), {"id": 5, "camera_id": 2}
        )
        connection.execute(
            metadata.tables["operacoes"].insert(),
            {"id": 6, "nome": "Soldagem", "area_risco_id": 5},
        )
        connection.execute(
            metadata.tables["alertas"].insert(), {"id": 8, "ocorrencia_id": 4}
        )
        connection.execute(
            metadata.tables["alertas_ingestao"].insert(),
            {
                "evento_id": "00000000-0000-0000-0000-000000000009",
                "alerta_id": 8,
                "operador_usuario_id": 7,
                "operacao_id": 6,
            },
        )


@pytest.fixture
def database_pair() -> Iterator[tuple[Engine, Engine]]:
    local = _engine(_schema())
    cloud = _engine(_schema())
    _seed_local(local)
    try:
        yield local, cloud
    finally:
        local.dispose()
        cloud.dispose()


def _count(engine: Engine, table_name: str) -> int:
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.connect() as connection:
        return int(connection.scalar(select(func.count()).select_from(metadata.tables[table_name])))


def test_sync_order_matches_real_foreign_key_dependencies() -> None:
    assert SYNC_TABLE_ORDER == (
        "usuarios",
        "setores",
        "cameras",
        "funcionarios",
        "ocorrencias",
        "areas_risco",
        "operacoes",
        "alertas",
        "alertas_ingestao",
    )


def test_dry_run_reports_counts_without_writing(database_pair: tuple[Engine, Engine]) -> None:
    local, cloud = database_pair

    report = synchronize_engines(local, cloud, masked_cloud_target="db.pr***", dry_run=True)

    assert tuple(item.table_name for item in report.tables) == SYNC_TABLE_ORDER
    assert all(item.source_count == 1 for item in report.tables)
    assert all(_count(cloud, name) == 0 for name in SYNC_TABLE_ORDER)


def test_dry_run_output_contains_only_masked_target_order_and_predicted_counts() -> None:
    report = SynchronizationReport(
        masked_cloud_target="db.pr***.supabase.co:5432/postgres",
        dry_run=True,
        tables=(TableSyncResult("usuarios", 2, 99),),
    )

    output = format_sync_report(report)

    assert output == (
        "Destino cloud: db.pr***.supabase.co:5432/postgres\n"
        "Modo: dry-run (nenhuma escrita)\n"
        "Ordem e quantidades previstas:\n"
        "- usuarios: prevista=2"
    )
    assert "cloud=99" not in output


def test_two_runs_are_idempotent_and_fixture_update_uses_upsert(
    database_pair: tuple[Engine, Engine],
) -> None:
    local, cloud = database_pair

    first = synchronize_engines(local, cloud, masked_cloud_target="db.pr***", dry_run=False)
    second = synchronize_engines(local, cloud, masked_cloud_target="db.pr***", dry_run=False)

    assert [item.cloud_count for item in first.tables] == [1] * len(SYNC_TABLE_ORDER)
    assert second.tables == first.tables
    assert all(_count(cloud, name) == 1 for name in SYNC_TABLE_ORDER)

    local_metadata = MetaData()
    local_metadata.reflect(local)
    with local.begin() as connection:
        connection.execute(
            update(local_metadata.tables["usuarios"])
            .where(local_metadata.tables["usuarios"].c.id == 7)
            .values(nome="Admin Atualizado")
        )
    synchronize_engines(local, cloud, masked_cloud_target="db.pr***", dry_run=False)

    cloud_metadata = MetaData()
    cloud_metadata.reflect(cloud)
    with cloud.connect() as connection:
        row = connection.execute(select(cloud_metadata.tables["usuarios"])).mappings().one()
    assert row["nome"] == "Admin Atualizado"
    assert row["senha_hash"] == "$2b$12$hash-preservado"


def test_failure_rolls_back_every_table() -> None:
    local = _engine(_schema())
    cloud = _engine(_schema(reject_employee=True))
    _seed_local(local, employee_name="rejeitar")
    try:
        with pytest.raises(IntegrityError):
            synchronize_engines(local, cloud, masked_cloud_target="db.pr***", dry_run=False)

        assert all(_count(cloud, name) == 0 for name in SYNC_TABLE_ORDER)
    finally:
        local.dispose()
        cloud.dispose()


def test_missing_admin_auth_column_is_rejected_before_writing() -> None:
    local = _engine(_schema(include_password_hash=False))
    cloud = _engine(_schema())
    try:
        with pytest.raises(SynchronizationError, match="usuarios"):
            synchronize_engines(local, cloud, masked_cloud_target="db.pr***", dry_run=False)

        assert all(_count(cloud, name) == 0 for name in SYNC_TABLE_ORDER)
    finally:
        local.dispose()
        cloud.dispose()
