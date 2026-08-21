"""Read-only PostgreSQL schema inspection used during API integration planning."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import DatabaseManager, DatabaseUnavailableError


def _text_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value]


def inspect_database_schema(
    database: DatabaseManager,
    schema: str,
) -> dict[str, Any]:
    """Return metadata only; never read application rows or mutate the database."""

    try:
        with database.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                inspector = inspect(connection)
                table_names = sorted(inspector.get_table_names(schema=schema))
                tables: list[dict[str, Any]] = []

                for table_name in table_names:
                    columns = []
                    for column in inspector.get_columns(table_name, schema=schema):
                        column_type = column["type"]
                        column_metadata: dict[str, Any] = {
                            "name": str(column["name"]),
                            "type": str(column_type),
                            "nullable": bool(column.get("nullable", True)),
                            "default": _text_or_none(column.get("default")),
                            "autoincrement": _text_or_none(column.get("autoincrement")),
                        }
                        timezone = getattr(column_type, "timezone", None)
                        if timezone is not None:
                            column_metadata["timezone"] = bool(timezone)
                        columns.append(column_metadata)

                    primary_key = inspector.get_pk_constraint(table_name, schema=schema)
                    foreign_keys = []
                    for foreign_key in inspector.get_foreign_keys(table_name, schema=schema):
                        foreign_keys.append(
                            {
                                "name": _text_or_none(foreign_key.get("name")),
                                "constrained_columns": _string_list(
                                    foreign_key.get("constrained_columns")
                                ),
                                "referred_schema": _text_or_none(
                                    foreign_key.get("referred_schema")
                                ),
                                "referred_table": _text_or_none(
                                    foreign_key.get("referred_table")
                                ),
                                "referred_columns": _string_list(
                                    foreign_key.get("referred_columns")
                                ),
                                "options": {
                                    str(key): str(value)
                                    for key, value in (foreign_key.get("options") or {}).items()
                                },
                            }
                        )

                    indexes = []
                    for index in inspector.get_indexes(table_name, schema=schema):
                        indexes.append(
                            {
                                "name": _text_or_none(index.get("name")),
                                "column_names": _string_list(index.get("column_names")),
                                "unique": bool(index.get("unique", False)),
                            }
                        )

                    unique_constraints = []
                    for unique_constraint in inspector.get_unique_constraints(
                        table_name, schema=schema
                    ):
                        unique_constraints.append(
                            {
                                "name": _text_or_none(unique_constraint.get("name")),
                                "column_names": _string_list(
                                    unique_constraint.get("column_names")
                                ),
                            }
                        )

                    check_constraints = []
                    for check_constraint in inspector.get_check_constraints(
                        table_name, schema=schema
                    ):
                        check_constraints.append(
                            {
                                "name": _text_or_none(check_constraint.get("name")),
                                "sqltext": _text_or_none(check_constraint.get("sqltext")),
                            }
                        )

                    tables.append(
                        {
                            "name": table_name,
                            "columns": columns,
                            "primary_key": {
                                "name": _text_or_none(primary_key.get("name")),
                                "constrained_columns": _string_list(
                                    primary_key.get("constrained_columns")
                                ),
                            },
                            "foreign_keys": foreign_keys,
                            "indexes": indexes,
                            "unique_constraints": unique_constraints,
                            "check_constraints": check_constraints,
                        }
                    )

                alembic_versions: list[str] = []
                if inspector.has_table("alembic_version", schema=schema):
                    rows = connection.execute(
                        text(f'SELECT version_num FROM "{schema}".alembic_version')
                    ).scalars()
                    alembic_versions = sorted(str(version) for version in rows)

                return {
                    "schema": schema,
                    "alembic_versions": alembic_versions,
                    "tables": tables,
                }
            finally:
                transaction.rollback()
    except SQLAlchemyError as error:
        raise DatabaseUnavailableError("não foi possível inspecionar o esquema") from error
