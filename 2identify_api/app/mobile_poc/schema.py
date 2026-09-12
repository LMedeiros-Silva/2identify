"""Canonical PostgreSQL schema snapshots used by the guarded cloud bootstrap."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from sqlalchemy import Connection, inspect, text


class SchemaConflictError(RuntimeError):
    """Raised when a cloud schema cannot be recognized without guessing."""


class CloudSchemaState(StrEnum):
    """Only physical states accepted by the mobile PoC bootstrap."""

    EMPTY = "empty"
    REVISION_42 = "42d54200970a"
    REVISION_441 = "441c04c14c57"
    HEAD = "e4a7b8c9d0e1"


@dataclass(frozen=True, order=True)
class ColumnSchema:
    name: str
    data_type: str
    nullable: bool
    default: str | None
    identity: tuple[tuple[str, str], ...] | None = None


@dataclass(frozen=True, order=True)
class ForeignKeySchema:
    name: str | None
    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]
    on_delete: str | None
    referred_schema: str | None = None


@dataclass(frozen=True, order=True)
class UniqueConstraintSchema:
    name: str | None
    columns: tuple[str, ...]


@dataclass(frozen=True, order=True)
class IndexSchema:
    name: str
    columns: tuple[str, ...]
    unique: bool
    included_columns: tuple[str, ...] = ()
    duplicates_constraint: str | None = None


@dataclass(frozen=True, order=True)
class TableSchema:
    name: str
    columns: tuple[ColumnSchema, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKeySchema, ...]
    unique_constraints: tuple[UniqueConstraintSchema, ...]
    indexes: tuple[IndexSchema, ...]


@dataclass(frozen=True, order=True)
class SequenceSchema:
    name: str
    data_type: str
    start_value: int
    increment_by: int
    cycle: bool
    min_value: int | None = None
    max_value: int | None = None
    cache_size: int | None = None


@dataclass(frozen=True)
class DatabaseSchemaSnapshot:
    tables: tuple[TableSchema, ...]
    sequences: tuple[SequenceSchema, ...]

    @classmethod
    def empty(cls) -> DatabaseSchemaSnapshot:
        return cls(tables=(), sequences=())

    def table(self, name: str) -> TableSchema:
        for table in self.tables:
            if table.name == name:
                return table
        raise KeyError(name)


_LATER_TABLES = frozenset(
    {"alertas_ingestao", "areas_risco", "operacoes", "operacao_epis"}
)
_LATER_ALERT_COLUMNS = frozenset({"confirmado_em", "confirmado_por"})
_LATER_ALERT_INDEXES = frozenset({"ix_alertas_status_criado_em"})
_LATER_ALERT_FOREIGN_KEYS = frozenset({"fk_alertas_confirmado_por_usuarios"})
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalized_default(value: object) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value).strip()).casefold()
    return normalized.replace("public.", "")


def _normalized_identity(value: object) -> tuple[tuple[str, str], ...] | None:
    if not isinstance(value, dict):
        return None
    return tuple(sorted((str(key), str(item)) for key, item in value.items()))


def _index_columns(item: Mapping[str, Any]) -> tuple[str, ...]:
    names = item.get("column_names") or ()
    expressions = iter(item.get("expressions") or ())
    resolved: list[str] = []
    for name in names:
        resolved.append(str(name) if name is not None else str(next(expressions, "")))
    return tuple(resolved)


def snapshot_postgresql_schema(
    connection: Connection,
    *,
    schema: str = "public",
) -> DatabaseSchemaSnapshot:
    """Read all application-facing structural metadata without mutating the database."""

    if _IDENTIFIER.fullmatch(schema) is None:
        raise ValueError("schema inválido")
    inspector = inspect(connection)
    table_names = sorted(
        name for name in inspector.get_table_names(schema=schema) if name != "alembic_version"
    )
    tables: list[TableSchema] = []
    for table_name in table_names:
        columns = tuple(
            sorted(
                (
                    ColumnSchema(
                        name=str(item["name"]),
                        data_type=str(item["type"]).casefold(),
                        nullable=bool(item["nullable"]),
                        default=_normalized_default(item.get("default")),
                        identity=_normalized_identity(item.get("identity")),
                    )
                    for item in inspector.get_columns(table_name, schema=schema)
                ),
                key=lambda item: item.name,
            )
        )
        pk = inspector.get_pk_constraint(table_name, schema=schema)
        foreign_keys = tuple(
            sorted(
                (
                    ForeignKeySchema(
                        name=item.get("name"),
                        columns=tuple(
                            str(value) for value in item.get("constrained_columns") or ()
                        ),
                        referred_table=str(item["referred_table"]),
                        referred_columns=tuple(
                            str(value) for value in item.get("referred_columns") or ()
                        ),
                        on_delete=(item.get("options") or {}).get("ondelete"),
                        referred_schema=item.get("referred_schema"),
                    )
                    for item in inspector.get_foreign_keys(table_name, schema=schema)
                ),
                key=lambda item: (item.name or "", item.columns),
            )
        )
        unique_constraints = tuple(
            sorted(
                (
                    UniqueConstraintSchema(
                        name=item.get("name"),
                        columns=tuple(str(value) for value in item.get("column_names") or ()),
                    )
                    for item in inspector.get_unique_constraints(table_name, schema=schema)
                ),
                key=lambda item: (item.name or "", item.columns),
            )
        )
        indexes = tuple(
            sorted(
                (
                    IndexSchema(
                        name=str(item["name"]),
                        columns=_index_columns(item),
                        unique=bool(item.get("unique")),
                        included_columns=tuple(
                            str(value) for value in item.get("include_columns") or ()
                        ),
                        duplicates_constraint=item.get("duplicates_constraint"),
                    )
                    for item in inspector.get_indexes(table_name, schema=schema)
                ),
                key=lambda item: item.name,
            )
        )
        tables.append(
            TableSchema(
                name=table_name,
                columns=columns,
                primary_key=tuple(str(value) for value in pk.get("constrained_columns") or ()),
                foreign_keys=foreign_keys,
                unique_constraints=unique_constraints,
                indexes=indexes,
            )
        )

    rows = connection.execute(
        text(
            "SELECT sequencename, data_type, start_value, min_value, max_value, "
            "increment_by, cycle, cache_size FROM pg_sequences "
            "WHERE schemaname = :schema ORDER BY sequencename"
        ),
        {"schema": schema},
    ).mappings()
    sequences = tuple(
        SequenceSchema(
            name=str(row["sequencename"]),
            data_type=str(row["data_type"]).casefold(),
            start_value=int(row["start_value"]),
            increment_by=int(row["increment_by"]),
            cycle=bool(row["cycle"]),
            min_value=int(row["min_value"]) if row["min_value"] is not None else None,
            max_value=int(row["max_value"]) if row["max_value"] is not None else None,
            cache_size=int(row["cache_size"]) if row["cache_size"] is not None else None,
        )
        for row in rows
    )
    return DatabaseSchemaSnapshot(tables=tuple(tables), sequences=sequences)


def read_alembic_revision(connection: Connection, *, schema: str = "public") -> str | None:
    """Return one Alembic revision, rejecting malformed or ambiguous version tables."""

    if _IDENTIFIER.fullmatch(schema) is None:
        raise ValueError("schema inválido")
    inspector = inspect(connection)
    if not inspector.has_table("alembic_version", schema=schema):
        return None
    rows = connection.execute(text(f'SELECT version_num FROM "{schema}".alembic_version')).scalars()
    revisions = tuple(str(value) for value in rows)
    if len(revisions) > 1:
        raise SchemaConflictError("tabela Alembic contém múltiplas revisões inesperadas")
    return revisions[0] if revisions else None


def project_head_snapshot_to_revision_441(
    snapshot: DatabaseSchemaSnapshot,
) -> DatabaseSchemaSnapshot:
    """Remove only objects introduced by the three approved post-stamp revisions."""

    tables: list[TableSchema] = []
    retained_names = {table.name for table in snapshot.tables} - _LATER_TABLES
    for table in snapshot.tables:
        if table.name not in retained_names:
            continue
        if table.name == "alertas":
            table = replace(
                table,
                columns=tuple(
                    item for item in table.columns if item.name not in _LATER_ALERT_COLUMNS
                ),
                foreign_keys=tuple(
                    item
                    for item in table.foreign_keys
                    if item.name not in _LATER_ALERT_FOREIGN_KEYS
                ),
                indexes=tuple(
                    item for item in table.indexes if item.name not in _LATER_ALERT_INDEXES
                ),
            )
        tables.append(table)
    retained_sequences = tuple(
        item
        for item in snapshot.sequences
        if not any(item.name.startswith(f"{table_name}_") for table_name in _LATER_TABLES)
    )
    return DatabaseSchemaSnapshot(
        tables=tuple(sorted(tables, key=lambda item: item.name)),
        sequences=tuple(sorted(retained_sequences, key=lambda item: item.name)),
    )


def diff_schema_snapshots(
    expected: DatabaseSchemaSnapshot,
    actual: DatabaseSchemaSnapshot,
) -> tuple[str, ...]:
    """Return semantic differences without leaking row data or credentials.

    PostgreSQL-generated and SQLAlchemy-convention names may differ for the same
    constraint.  Names remain captured in snapshots for auditing, but structural
    compatibility is based on the constrained columns, targets and actions.
    """

    def foreign_key_signatures(
        table: TableSchema,
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            sorted(
                (
                    item.columns,
                    item.referred_schema,
                    item.referred_table,
                    item.referred_columns,
                    item.on_delete,
                )
                for item in table.foreign_keys
            )
        )

    def unique_signatures(table: TableSchema) -> tuple[tuple[str, ...], ...]:
        return tuple(sorted(item.columns for item in table.unique_constraints))

    def index_signatures(
        table: TableSchema,
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            sorted(
                (item.columns, item.unique, item.included_columns)
                for item in table.indexes
            )
        )

    differences: list[str] = []
    expected_tables = {table.name: table for table in expected.tables}
    actual_tables = {table.name: table for table in actual.tables}
    if expected_tables.keys() != actual_tables.keys():
        differences.append("tables differ")
    for name in sorted(expected_tables.keys() & actual_tables.keys()):
        expected_table = expected_tables[name]
        actual_table = actual_tables[name]
        for field in ("columns", "primary_key"):
            if getattr(expected_table, field) != getattr(actual_table, field):
                differences.append(f"table {name}: {field} differ")
        if foreign_key_signatures(expected_table) != foreign_key_signatures(actual_table):
            differences.append(f"table {name}: foreign_keys differ")
        if unique_signatures(expected_table) != unique_signatures(actual_table):
            differences.append(f"table {name}: unique_constraints differ")
        if index_signatures(expected_table) != index_signatures(actual_table):
            differences.append(f"table {name}: indexes differ")
    if expected.sequences != actual.sequences:
        differences.append("sequences differ")
    return tuple(differences)


def classify_cloud_schema(
    actual: DatabaseSchemaSnapshot,
    revision: str | None,
    expected_revision_441: DatabaseSchemaSnapshot,
    expected_head: DatabaseSchemaSnapshot,
) -> CloudSchemaState:
    """Accept only the exact resumable states designed for this bootstrap."""

    if revision is None and actual == DatabaseSchemaSnapshot.empty():
        return CloudSchemaState.EMPTY
    expected_by_revision = {
        CloudSchemaState.REVISION_42.value: (
            CloudSchemaState.REVISION_42,
            expected_revision_441,
        ),
        CloudSchemaState.REVISION_441.value: (
            CloudSchemaState.REVISION_441,
            expected_revision_441,
        ),
        CloudSchemaState.HEAD.value: (CloudSchemaState.HEAD, expected_head),
    }
    matched = expected_by_revision.get(revision or "")
    if matched is None:
        raise SchemaConflictError("schema cloud possui revisão Alembic não reconhecida")
    state, expected = matched
    differences = diff_schema_snapshots(expected, actual)
    if differences:
        categories = ", ".join(differences)
        raise SchemaConflictError(f"schema cloud incompatível: {categories}")
    return state


__all__ = [
    "CloudSchemaState",
    "ColumnSchema",
    "DatabaseSchemaSnapshot",
    "ForeignKeySchema",
    "IndexSchema",
    "SchemaConflictError",
    "SequenceSchema",
    "TableSchema",
    "UniqueConstraintSchema",
    "classify_cloud_schema",
    "diff_schema_snapshots",
    "project_head_snapshot_to_revision_441",
    "read_alembic_revision",
    "snapshot_postgresql_schema",
]
