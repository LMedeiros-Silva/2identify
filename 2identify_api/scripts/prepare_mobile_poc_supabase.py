"""Safely inspect or bootstrap the mobile PoC schema in Supabase."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import PROJECT_ROOT
from app.mobile_poc.bootstrap import (
    BootstrapDatabaseState,
    BootstrapInfrastructure,
    run_mobile_poc_bootstrap,
)
from app.mobile_poc.config import (
    MobilePocConfigurationError,
    MobilePocDatabaseConfig,
    load_mobile_poc_database_config,
)
from app.mobile_poc.migrations import MigrationAuditError
from app.mobile_poc.schema import (
    SchemaConflictError,
    read_alembic_revision,
    snapshot_postgresql_schema,
)

VERSIONS_DIRECTORY = PROJECT_ROOT / "alembic" / "versions"


class BootstrapExecutionError(RuntimeError):
    """Safe high-level failure that deliberately omits connection details."""


class SqlAlchemyBootstrapInfrastructure(BootstrapInfrastructure):
    def __init__(self, config: MobilePocDatabaseConfig, *, schema: str = "public") -> None:
        self._config = config
        self._schema = schema

    def _read_state(self, url: str) -> BootstrapDatabaseState:
        engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    snapshot = snapshot_postgresql_schema(connection, schema=self._schema)
                    revision = read_alembic_revision(connection, schema=self._schema)
                finally:
                    transaction.rollback()
        except SQLAlchemyError as error:
            raise BootstrapExecutionError(
                "não foi possível inspecionar um dos bancos configurados"
            ) from error
        finally:
            engine.dispose()
        return BootstrapDatabaseState(snapshot, revision)

    def read_local_state(self) -> BootstrapDatabaseState:
        return self._read_state(self._config.local_sqlalchemy_url)

    def read_cloud_state(self) -> BootstrapDatabaseState:
        return self._read_state(self._config.cloud_sqlalchemy_url)

    def run_alembic(self, action: str, revision: str) -> None:
        if (action, revision) not in {
            ("upgrade", "42d54200970a"),
            ("stamp", "441c04c14c57"),
            ("upgrade", "e4a7b8c9d0e1"),
        }:
            raise BootstrapExecutionError("ação Alembic fora do fluxo aprovado")
        child_environment = dict(os.environ)
        child_environment["DATABASE_URL"] = self._config.cloud_sqlalchemy_url
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", action, revision],
            cwd=PROJECT_ROOT,
            env=child_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise BootstrapExecutionError(
                f"Alembic falhou durante {action} da revision solicitada"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="somente inspeciona e audita (padrão)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="executa exclusivamente o bootstrap Alembic aprovado",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_mobile_poc_database_config()
        infrastructure = SqlAlchemyBootstrapInfrastructure(config)
        report = run_mobile_poc_bootstrap(
            config,
            infrastructure,
            versions_directory=VERSIONS_DIRECTORY,
            apply=args.apply,
        )
    except (
        BootstrapExecutionError,
        MigrationAuditError,
        MobilePocConfigurationError,
        SchemaConflictError,
    ) as error:
        print(f"PREPARAÇÃO INTERROMPIDA: {type(error).__name__}", file=sys.stderr)
        return 2

    print(f"Destino cloud: {report.masked_cloud_target}")
    print(f"Estado inicial: {report.initial_state}")
    print(f"Estado final: {report.final_state}")
    if args.apply:
        print("Executadas antes do stamp: " + ", ".join(report.executed_before_stamp))
        print("Puladas via stamp: " + ", ".join(report.stamped_over))
        print("Executadas após o stamp: " + ", ".join(report.executed_after_stamp))
    else:
        print("Preflight somente leitura concluído; nenhuma DDL executada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
