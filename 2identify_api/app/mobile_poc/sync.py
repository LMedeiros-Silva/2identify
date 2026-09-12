"""Selective PostgreSQL-to-PostgreSQL synchronization for the mobile PoC."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, MetaData, Table, and_, func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


class SynchronizationError(RuntimeError):
    """Raised when selective synchronization cannot be proven safe."""


SYNC_TABLE_ORDER = (
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
_SYNC_TABLE_SET = frozenset(SYNC_TABLE_ORDER)
_ADMIN_AUTH_COLUMNS = frozenset(
    {"id", "nome", "username", "senha_hash", "perfil", "ativo"}
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class TableSyncResult:
    table_name: str
    source_count: int
    cloud_count: int


@dataclass(frozen=True)
class SequenceSyncResult:
    table_name: str
    column_name: str
    sequence_name: str
    value: int


@dataclass(frozen=True)
class SynchronizationReport:
    masked_cloud_target: str
    dry_run: bool
    tables: tuple[TableSyncResult, ...]
    sequences: tuple[SequenceSyncResult, ...] = ()


def _reflect_tables(
    connection: Connection,
    *,
    schema: str | None,
) -> dict[str, Table]:
    existing = frozenset(inspect(connection).get_table_names(schema=schema))
    missing = _SYNC_TABLE_SET - existing
    if missing:
        raise SynchronizationError(
            "schema não contém todas as tabelas necessárias: " + ", ".join(sorted(missing))
        )
    metadata = MetaData()
    metadata.reflect(bind=connection, schema=schema, only=SYNC_TABLE_ORDER)
    return {
        name: metadata.tables[f"{schema}.{name}" if schema else name] for name in SYNC_TABLE_ORDER
    }


def _column_signature(table: Table) -> tuple[tuple[str, str, bool], ...]:
    return tuple(
        (column.name, str(column.type).casefold(), bool(column.nullable))
        for column in table.columns
    )


def _validate_contract(local_tables: dict[str, Table], cloud_tables: dict[str, Table]) -> None:
    if not _ADMIN_AUTH_COLUMNS.issubset(local_tables["usuarios"].c.keys()):
        raise SynchronizationError("tabela usuarios não contém o contrato de autenticação Admin")
    positions = {name: index for index, name in enumerate(SYNC_TABLE_ORDER)}
    for name in SYNC_TABLE_ORDER:
        local_table = local_tables[name]
        cloud_table = cloud_tables[name]
        if _column_signature(local_table) != _column_signature(cloud_table):
            raise SynchronizationError(f"estrutura da tabela {name} difere entre origem e cloud")
        local_pk = tuple(column.name for column in local_table.primary_key.columns)
        cloud_pk = tuple(column.name for column in cloud_table.primary_key.columns)
        if not local_pk or local_pk != cloud_pk:
            raise SynchronizationError(f"chave primária incompatível na tabela {name}")
        for foreign_key in local_table.foreign_key_constraints:
            target_name = foreign_key.referred_table.name
            if target_name not in _SYNC_TABLE_SET:
                raise SynchronizationError(
                    f"tabela {name} depende de tabela não permitida na sincronização"
                )
            if positions[target_name] >= positions[name]:
                raise SynchronizationError(
                    f"ordem de sincronização não respeita a dependência de {name}"
                )


def _read_rows(connection: Connection, table: Table) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(select(table)).mappings()]


def _upsert_rows(connection: Connection, table: Table, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    primary_key = tuple(column.name for column in table.primary_key.columns)
    if connection.dialect.name == "postgresql":
        statement: Any = postgresql_insert(table).values(rows)
    elif connection.dialect.name == "sqlite":
        statement = sqlite_insert(table).values(rows)
    else:
        raise SynchronizationError("dialeto cloud não suportado")
    assignments = {
        column.name: getattr(statement.excluded, column.name)
        for column in table.columns
        if column.name not in primary_key
    }
    if assignments:
        statement = statement.on_conflict_do_update(
            index_elements=[table.c[name] for name in primary_key],
            set_=assignments,
        )
    else:
        statement = statement.on_conflict_do_nothing(
            index_elements=[table.c[name] for name in primary_key]
        )
    connection.execute(statement)


def _count(connection: Connection, table: Table) -> int:
    return int(connection.scalar(select(func.count()).select_from(table)) or 0)


def _validate_foreign_keys(connection: Connection, tables: dict[str, Table]) -> None:
    for table_name in SYNC_TABLE_ORDER:
        source_table = tables[table_name]
        for constraint in source_table.foreign_key_constraints:
            target_table = tables[constraint.referred_table.name]
            source = source_table.alias("source_rows")
            target = target_table.alias("target_rows")
            pairs = tuple(constraint.elements)
            join_condition = and_(
                *(
                    source.c[item.parent.name] == target.c[item.column.name]
                    for item in pairs
                )
            )
            source_has_values = and_(
                *(source.c[item.parent.name].is_not(None) for item in pairs)
            )
            first_target_column = target.c[pairs[0].column.name]
            statement = (
                select(func.count())
                .select_from(source.outerjoin(target, join_condition))
                .where(source_has_values, first_target_column.is_(None))
            )
            if int(connection.scalar(statement) or 0) != 0:
                raise SynchronizationError(
                    f"integridade referencial inválida após sincronizar {table_name}"
                )


def _safe_sequence_name(value: str) -> tuple[str, str]:
    pieces = value.split(".", maxsplit=1)
    if len(pieces) == 1:
        pieces = ["public", pieces[0]]
    if any(_IDENTIFIER.fullmatch(piece) is None for piece in pieces):
        raise SynchronizationError("sequence PostgreSQL possui nome inesperado")
    return pieces[0], pieces[1]


def _advance_postgresql_sequences(
    connection: Connection,
    tables: dict[str, Table],
    *,
    schema: str,
) -> tuple[SequenceSyncResult, ...]:
    results: list[SequenceSyncResult] = []
    for table_name in SYNC_TABLE_ORDER:
        table = tables[table_name]
        primary_key = tuple(table.primary_key.columns)
        if len(primary_key) != 1 or primary_key[0].type.python_type is not int:
            continue
        column = primary_key[0]
        qualified_table = f"{schema}.{table_name}"
        sequence = connection.scalar(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": qualified_table, "column_name": column.name},
        )
        if not isinstance(sequence, str):
            continue
        sequence_schema, sequence_name = _safe_sequence_name(sequence)
        quoted_schema = connection.dialect.identifier_preparer.quote(sequence_schema)
        quoted_sequence = connection.dialect.identifier_preparer.quote(sequence_name)
        current_value, is_called = connection.execute(
            text(f"SELECT last_value, is_called FROM {quoted_schema}.{quoted_sequence}")
        ).one()
        maximum_id = connection.scalar(select(func.max(column)))
        value = max(int(current_value), int(maximum_id) if maximum_id is not None else 1)
        called = bool(is_called or maximum_id is not None)
        connection.execute(
            text(
                "SELECT setval(CAST(:sequence_name AS regclass), :value, :is_called)"
            ),
            {
                "sequence_name": f"{sequence_schema}.{sequence_name}",
                "value": value,
                "is_called": called,
            },
        )
        results.append(
            SequenceSyncResult(table_name, column.name, sequence_name, value)
        )
    return tuple(results)


def synchronize_connections(
    local_connection: Connection,
    cloud_connection: Connection,
    *,
    masked_cloud_target: str,
    dry_run: bool,
    schema: str | None = None,
) -> SynchronizationReport:
    """Synchronize within caller-owned transactions without committing or deleting rows."""

    local_tables = _reflect_tables(local_connection, schema=schema)
    cloud_tables = _reflect_tables(cloud_connection, schema=schema)
    _validate_contract(local_tables, cloud_tables)
    source_rows = {
        name: _read_rows(local_connection, local_tables[name]) for name in SYNC_TABLE_ORDER
    }
    if not dry_run:
        for name in SYNC_TABLE_ORDER:
            _upsert_rows(cloud_connection, cloud_tables[name], source_rows[name])
        _validate_foreign_keys(cloud_connection, cloud_tables)
    table_results = tuple(
        TableSyncResult(
            table_name=name,
            source_count=len(source_rows[name]),
            cloud_count=_count(cloud_connection, cloud_tables[name]),
        )
        for name in SYNC_TABLE_ORDER
    )
    sequences: tuple[SequenceSyncResult, ...] = ()
    if not dry_run and cloud_connection.dialect.name == "postgresql":
        sequences = _advance_postgresql_sequences(
            cloud_connection,
            cloud_tables,
            schema=schema or "public",
        )
    return SynchronizationReport(
        masked_cloud_target=masked_cloud_target,
        dry_run=dry_run,
        tables=table_results,
        sequences=sequences,
    )


def synchronize_engines(
    local_engine: Engine,
    cloud_engine: Engine,
    *,
    masked_cloud_target: str,
    dry_run: bool,
    schema: str | None = None,
) -> SynchronizationReport:
    """Own the read-only source transaction and one atomic cloud transaction."""

    with local_engine.connect() as local_connection:
        local_transaction = local_connection.begin()
        try:
            if local_connection.dialect.name == "postgresql":
                local_connection.execute(text("SET TRANSACTION READ ONLY"))
            if dry_run:
                with cloud_engine.connect() as cloud_connection:
                    return synchronize_connections(
                        local_connection,
                        cloud_connection,
                        masked_cloud_target=masked_cloud_target,
                        dry_run=True,
                        schema=schema,
                    )
            with cloud_engine.begin() as cloud_connection:
                return synchronize_connections(
                    local_connection,
                    cloud_connection,
                    masked_cloud_target=masked_cloud_target,
                    dry_run=False,
                    schema=schema,
                )
        finally:
            local_transaction.rollback()


__all__ = [
    "SYNC_TABLE_ORDER",
    "SequenceSyncResult",
    "SynchronizationError",
    "SynchronizationReport",
    "TableSyncResult",
    "synchronize_connections",
    "synchronize_engines",
]
