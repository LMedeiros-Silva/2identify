"""Behavior tests for strict cloud schema recognition."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.mobile_poc.schema import (
    CloudSchemaState,
    ColumnSchema,
    DatabaseSchemaSnapshot,
    ForeignKeySchema,
    IndexSchema,
    SchemaConflictError,
    SequenceSchema,
    TableSchema,
    UniqueConstraintSchema,
    classify_cloud_schema,
    diff_schema_snapshots,
    project_head_snapshot_to_revision_441,
)


def _head_snapshot() -> DatabaseSchemaSnapshot:
    users = TableSchema(
        name="usuarios",
        columns=(
            ColumnSchema("id", "integer", False, "nextval('usuarios_id_seq'::regclass)"),
            ColumnSchema("username", "varchar(100)", False, None),
            ColumnSchema("atualizado_em", "timestamp with time zone", False, None),
        ),
        primary_key=("id",),
        foreign_keys=(),
        unique_constraints=(),
        indexes=(IndexSchema("ix_usuarios_username", ("username",), True),),
    )
    alerts = TableSchema(
        name="alertas",
        columns=(
            ColumnSchema("id", "integer", False, "nextval('alertas_id_seq'::regclass)"),
            ColumnSchema("ocorrencia_id", "integer", False, None),
            ColumnSchema("confirmado_em", "timestamp with time zone", True, None),
            ColumnSchema("confirmado_por", "integer", True, None),
        ),
        primary_key=("id",),
        foreign_keys=(
            ForeignKeySchema(
                "fk_alertas_confirmado_por_usuarios",
                ("confirmado_por",),
                "usuarios",
                ("id",),
                "SET NULL",
            ),
        ),
        unique_constraints=(
            UniqueConstraintSchema("alertas_ocorrencia_id_key", ("ocorrencia_id",)),
        ),
        indexes=(
            IndexSchema("ix_alertas_status_criado_em", ("status", "criado_em"), False),
        ),
    )
    ingestion = TableSchema(
        name="alertas_ingestao",
        columns=(ColumnSchema("evento_id", "uuid", False, None),),
        primary_key=("evento_id",),
        foreign_keys=(),
        unique_constraints=(),
        indexes=(),
    )
    operations = TableSchema(
        name="operacoes",
        columns=(ColumnSchema("id", "integer", False, "nextval('operacoes_id_seq')"),),
        primary_key=("id",),
        foreign_keys=(),
        unique_constraints=(),
        indexes=(),
    )
    return DatabaseSchemaSnapshot(
        tables=(users, alerts, ingestion, operations),
        sequences=(
            SequenceSchema("alertas_id_seq", "integer", 1, 1, False),
            SequenceSchema("operacoes_id_seq", "integer", 1, 1, False),
            SequenceSchema("usuarios_id_seq", "integer", 1, 1, False),
        ),
    )


def test_projection_to_revision_441_removes_only_later_schema_changes() -> None:
    projected = project_head_snapshot_to_revision_441(_head_snapshot())

    assert tuple(table.name for table in projected.tables) == ("alertas", "usuarios")
    alerts = projected.table("alertas")
    assert tuple(column.name for column in alerts.columns) == ("id", "ocorrencia_id")
    assert alerts.foreign_keys == ()
    assert alerts.indexes == ()
    assert tuple(sequence.name for sequence in projected.sequences) == (
        "alertas_id_seq",
        "usuarios_id_seq",
    )


def test_schema_diff_detects_each_structural_category() -> None:
    expected = _head_snapshot()
    users = expected.table("usuarios")
    changed_users = replace(
        users,
        columns=(replace(users.columns[0], nullable=True), *users.columns[1:]),
        primary_key=(),
        indexes=(),
    )
    actual = replace(
        expected,
        tables=(changed_users, *expected.tables[1:]),
        sequences=(),
    )

    differences = diff_schema_snapshots(expected, actual)

    assert any("columns" in item for item in differences)
    assert any("primary_key" in item for item in differences)
    assert any("indexes" in item for item in differences)
    assert any("sequences" in item for item in differences)


def test_only_empty_revision_42_stamped_stage_or_head_are_recognized() -> None:
    head = _head_snapshot()
    stage = project_head_snapshot_to_revision_441(head)

    assert (
        classify_cloud_schema(DatabaseSchemaSnapshot.empty(), None, stage, head)
        is CloudSchemaState.EMPTY
    )
    assert (
        classify_cloud_schema(stage, "42d54200970a", stage, head)
        is CloudSchemaState.REVISION_42
    )
    assert (
        classify_cloud_schema(stage, "441c04c14c57", stage, head)
        is CloudSchemaState.REVISION_441
    )
    assert (
        classify_cloud_schema(head, "e4a7b8c9d0e1", stage, head)
        is CloudSchemaState.HEAD
    )


def test_unknown_revision_or_physical_difference_is_rejected() -> None:
    head = _head_snapshot()
    stage = project_head_snapshot_to_revision_441(head)

    with pytest.raises(SchemaConflictError):
        classify_cloud_schema(stage, "unexpected", stage, head)

    damaged = replace(stage, sequences=())
    with pytest.raises(SchemaConflictError):
        classify_cloud_schema(damaged, "42d54200970a", stage, head)


def test_equivalent_constraint_names_do_not_create_false_schema_conflict() -> None:
    head = _head_snapshot()
    alerts = head.table("alertas")
    renamed_alerts = replace(
        alerts,
        foreign_keys=(
            replace(alerts.foreign_keys[0], name="alertas_confirmado_por_fkey"),
        ),
        unique_constraints=(
            replace(
                alerts.unique_constraints[0],
                name="uq_alertas_ocorrencia_id",
            ),
        ),
        indexes=(
            replace(
                alerts.indexes[0],
                name="idx_alertas_status_criado_em",
                duplicates_constraint="uq_alertas_ocorrencia_id",
            ),
        ),
    )
    actual = replace(
        head,
        tables=tuple(
            renamed_alerts if table.name == "alertas" else table
            for table in head.tables
        ),
    )

    assert diff_schema_snapshots(head, actual) == ()
    assert (
        classify_cloud_schema(
            actual,
            "e4a7b8c9d0e1",
            project_head_snapshot_to_revision_441(head),
            head,
        )
        is CloudSchemaState.HEAD
    )

    changed_action = replace(
        actual,
        tables=tuple(
            replace(
                renamed_alerts,
                foreign_keys=(
                    replace(renamed_alerts.foreign_keys[0], on_delete="CASCADE"),
                ),
            )
            if table.name == "alertas"
            else table
            for table in actual.tables
        ),
    )
    assert "table alertas: foreign_keys differ" in diff_schema_snapshots(
        head,
        changed_action,
    )
