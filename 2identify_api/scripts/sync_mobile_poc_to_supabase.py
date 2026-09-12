"""Manually synchronize the approved alert subset from local PostgreSQL to Supabase."""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.mobile_poc.config import MobilePocConfigurationError, load_mobile_poc_database_config
from app.mobile_poc.schema import (
    CloudSchemaState,
    SchemaConflictError,
    classify_cloud_schema,
    project_head_snapshot_to_revision_441,
)
from app.mobile_poc.sync import (
    SynchronizationError,
    SynchronizationReport,
    synchronize_engines,
)
from scripts.prepare_mobile_poc_supabase import (
    BootstrapExecutionError,
    SqlAlchemyBootstrapInfrastructure,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="somente planeja (padrão)")
    mode.add_argument("--apply", action="store_true", help="executa upserts no cloud")
    return parser


def format_sync_report(report: SynchronizationReport) -> str:
    """Format only non-sensitive counts appropriate for the selected mode."""

    lines = [
        f"Destino cloud: {report.masked_cloud_target}",
        "Modo: " + ("dry-run (nenhuma escrita)" if report.dry_run else "upsert transacional"),
    ]
    if report.dry_run:
        lines.append("Ordem e quantidades previstas:")
        lines.extend(
            f"- {item.table_name}: prevista={item.source_count}" for item in report.tables
        )
    else:
        lines.append("Ordem e contagens validadas:")
        lines.extend(
            f"- {item.table_name}: origem={item.source_count}, cloud={item.cloud_count}"
            for item in report.tables
        )
        if report.sequences:
            lines.append(f"Sequences validadas/avançadas: {len(report.sequences)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_mobile_poc_database_config()
        settings = Settings()
        infrastructure = SqlAlchemyBootstrapInfrastructure(
            config,
            schema=settings.database_schema,
        )
        local_state = infrastructure.read_local_state()
        if local_state.revision != CloudSchemaState.HEAD.value:
            raise SchemaConflictError("banco local não está no head aprovado")
        cloud_state = infrastructure.read_cloud_state()
        expected_stage = project_head_snapshot_to_revision_441(local_state.snapshot)
        state = classify_cloud_schema(
            cloud_state.snapshot,
            cloud_state.revision,
            expected_stage,
            local_state.snapshot,
        )
        if state is not CloudSchemaState.HEAD:
            raise SchemaConflictError("schema cloud ainda não está no head aprovado")

        local_engine = create_engine(
            config.local_sqlalchemy_url,
            pool_pre_ping=True,
            hide_parameters=True,
        )
        cloud_engine = create_engine(
            config.cloud_sqlalchemy_url,
            pool_pre_ping=True,
            hide_parameters=True,
        )
        try:
            report = synchronize_engines(
                local_engine,
                cloud_engine,
                masked_cloud_target=config.masked_cloud_target,
                dry_run=not args.apply,
                schema=settings.database_schema,
            )
        finally:
            local_engine.dispose()
            cloud_engine.dispose()
    except (
        BootstrapExecutionError,
        MobilePocConfigurationError,
        SchemaConflictError,
        SQLAlchemyError,
        SynchronizationError,
    ) as error:
        print(f"SINCRONIZAÇÃO INTERROMPIDA: {type(error).__name__}", file=sys.stderr)
        return 2

    print(format_sync_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
