"""Guarded Alembic bootstrap workflow for the Supabase mobile PoC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.mobile_poc.config import MobilePocDatabaseConfig
from app.mobile_poc.migrations import (
    MigrationAuditError,
    audit_migration_upgrade,
    audit_post_stamp_migrations,
    read_migration_metadata,
)
from app.mobile_poc.schema import (
    CloudSchemaState,
    DatabaseSchemaSnapshot,
    SchemaConflictError,
    classify_cloud_schema,
    project_head_snapshot_to_revision_441,
)

_HEAD = "e4a7b8c9d0e1"
_REVISION_42 = "42d54200970a"
_REVISION_441 = "441c04c14c57"
_BEFORE_STAMP = ("5e2716b5ed84", _REVISION_42)
_STAMPED_OVER = ("d5338781e8f0", _REVISION_441)


@dataclass(frozen=True)
class BootstrapDatabaseState:
    snapshot: DatabaseSchemaSnapshot
    revision: str | None

    @classmethod
    def empty(cls) -> BootstrapDatabaseState:
        return cls(DatabaseSchemaSnapshot.empty(), None)


@dataclass(frozen=True)
class BootstrapReport:
    masked_cloud_target: str
    initial_state: str
    final_state: str
    executed_before_stamp: tuple[str, ...]
    stamped_over: tuple[str, ...]
    executed_after_stamp: tuple[str, ...]


class BootstrapInfrastructure(Protocol):
    def read_local_state(self) -> BootstrapDatabaseState:
        """Return the read-only local schema and revision."""

    def read_cloud_state(self) -> BootstrapDatabaseState:
        """Return the read-only cloud schema and revision."""

    def run_alembic(self, action: str, revision: str) -> None:
        """Run one already-approved Alembic action against cloud."""


def _migration_index(versions_directory: Path) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for path in sorted(versions_directory.glob("*.py")):
        metadata = read_migration_metadata(path)
        if metadata.revision in indexed:
            raise MigrationAuditError("revision Alembic duplicada")
        indexed[metadata.revision] = path
    return indexed


def _audit_full_approved_plan(versions_directory: Path) -> tuple[str, ...]:
    indexed = _migration_index(versions_directory)
    required = {*_BEFORE_STAMP, *_STAMPED_OVER}
    if not required.issubset(indexed):
        raise MigrationAuditError("cadeia Alembic aprovada está incompleta")
    metadata = {revision: read_migration_metadata(indexed[revision]) for revision in required}
    if (
        metadata["5e2716b5ed84"].down_revision is not None
        or metadata[_REVISION_42].down_revision != "5e2716b5ed84"
        or metadata["d5338781e8f0"].down_revision != _REVISION_42
        or metadata[_REVISION_441].down_revision != "d5338781e8f0"
    ):
        raise MigrationAuditError("par de revisions puladas não é o par aprovado")
    audit_migration_upgrade(indexed["5e2716b5ed84"])
    audit_migration_upgrade(
        indexed[_REVISION_42],
        allowed_call_names=frozenset({"alter_column"}),
    )
    return audit_post_stamp_migrations(versions_directory)


def run_mobile_poc_bootstrap(
    config: MobilePocDatabaseConfig,
    infrastructure: BootstrapInfrastructure,
    *,
    versions_directory: Path,
    apply: bool,
) -> BootstrapReport:
    """Validate and optionally advance cloud through the one approved migration path."""

    local = infrastructure.read_local_state()
    if local.revision != _HEAD:
        raise SchemaConflictError("banco local não está na revision Alembic aprovada")
    expected_head = local.snapshot
    expected_revision_441 = project_head_snapshot_to_revision_441(expected_head)
    post_stamp_revisions = _audit_full_approved_plan(versions_directory)

    cloud = infrastructure.read_cloud_state()
    initial_state = classify_cloud_schema(
        cloud.snapshot,
        cloud.revision,
        expected_revision_441,
        expected_head,
    )
    if not apply:
        return BootstrapReport(
            masked_cloud_target=config.masked_cloud_target,
            initial_state=initial_state.value,
            final_state=initial_state.value,
            executed_before_stamp=(),
            stamped_over=(),
            executed_after_stamp=(),
        )

    executed_before: tuple[str, ...] = ()
    stamped_over: tuple[str, ...] = ()
    executed_after: tuple[str, ...] = ()
    current_state = initial_state

    if current_state is CloudSchemaState.EMPTY:
        infrastructure.run_alembic("upgrade", _REVISION_42)
        executed_before = _BEFORE_STAMP
        cloud = infrastructure.read_cloud_state()
        current_state = classify_cloud_schema(
            cloud.snapshot,
            cloud.revision,
            expected_revision_441,
            expected_head,
        )
        if current_state is not CloudSchemaState.REVISION_42:
            raise SchemaConflictError("upgrade inicial não produziu o schema físico esperado")

    if current_state is CloudSchemaState.REVISION_42:
        infrastructure.run_alembic("stamp", _REVISION_441)
        stamped_over = _STAMPED_OVER
        cloud = infrastructure.read_cloud_state()
        current_state = classify_cloud_schema(
            cloud.snapshot,
            cloud.revision,
            expected_revision_441,
            expected_head,
        )
        if current_state is not CloudSchemaState.REVISION_441:
            raise SchemaConflictError("stamp não preservou o schema físico esperado")

    if current_state is CloudSchemaState.REVISION_441:
        infrastructure.run_alembic("upgrade", _HEAD)
        executed_after = post_stamp_revisions
        cloud = infrastructure.read_cloud_state()
        current_state = classify_cloud_schema(
            cloud.snapshot,
            cloud.revision,
            expected_revision_441,
            expected_head,
        )

    if current_state is not CloudSchemaState.HEAD:
        raise SchemaConflictError("bootstrap não alcançou o head Alembic aprovado")
    return BootstrapReport(
        masked_cloud_target=config.masked_cloud_target,
        initial_state=initial_state.value,
        final_state=current_state.value,
        executed_before_stamp=executed_before,
        stamped_over=stamped_over,
        executed_after_stamp=executed_after,
    )


__all__ = [
    "BootstrapDatabaseState",
    "BootstrapInfrastructure",
    "BootstrapReport",
    "run_mobile_poc_bootstrap",
]
