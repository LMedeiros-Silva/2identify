"""Tests for the guarded and resumable Supabase Alembic bootstrap."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.mobile_poc.bootstrap import (
    BootstrapDatabaseState,
    BootstrapReport,
    run_mobile_poc_bootstrap,
)
from app.mobile_poc.config import validate_mobile_database_targets
from app.mobile_poc.schema import (
    ColumnSchema,
    DatabaseSchemaSnapshot,
    SchemaConflictError,
    SequenceSchema,
    TableSchema,
)

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
CONFIG = validate_mobile_database_targets(
    "postgresql://local:one@127.0.0.1:5432/identify",
    "postgresql://cloud:two@db.projectref.supabase.co:5432/postgres",
)


def _head() -> DatabaseSchemaSnapshot:
    return DatabaseSchemaSnapshot(
        tables=(
            TableSchema(
                name="usuarios",
                columns=(
                    ColumnSchema("id", "integer", False, "nextval('usuarios_id_seq')"),
                    ColumnSchema("atualizado_em", "timestamp with time zone", False, None),
                ),
                primary_key=("id",),
                foreign_keys=(),
                unique_constraints=(),
                indexes=(),
            ),
        ),
        sequences=(SequenceSchema("usuarios_id_seq", "integer", 1, 1, False),),
    )


class FakeInfrastructure:
    def __init__(self, cloud_states: tuple[BootstrapDatabaseState, ...]) -> None:
        self._cloud_states: Iterator[BootstrapDatabaseState] = iter(cloud_states)
        self.commands: list[tuple[str, str]] = []

    def read_local_state(self) -> BootstrapDatabaseState:
        return BootstrapDatabaseState(_head(), "e4a7b8c9d0e1")

    def read_cloud_state(self) -> BootstrapDatabaseState:
        return next(self._cloud_states)

    def run_alembic(self, action: str, revision: str) -> None:
        self.commands.append((action, revision))


def test_preflight_only_never_executes_alembic_mutations() -> None:
    infrastructure = FakeInfrastructure(
        (BootstrapDatabaseState(DatabaseSchemaSnapshot.empty(), None),)
    )

    report = run_mobile_poc_bootstrap(
        CONFIG,
        infrastructure,
        versions_directory=VERSIONS,
        apply=False,
    )

    assert report.initial_state == "empty"
    assert report.final_state == "empty"
    assert report.executed_before_stamp == ()
    assert infrastructure.commands == []


def test_empty_cloud_runs_only_approved_sequence_after_every_guard() -> None:
    head = _head()
    empty = BootstrapDatabaseState(DatabaseSchemaSnapshot.empty(), None)
    revision_42 = BootstrapDatabaseState(head, "42d54200970a")
    revision_441 = BootstrapDatabaseState(head, "441c04c14c57")
    final = BootstrapDatabaseState(head, "e4a7b8c9d0e1")
    infrastructure = FakeInfrastructure((empty, revision_42, revision_441, final))

    report = run_mobile_poc_bootstrap(
        CONFIG,
        infrastructure,
        versions_directory=VERSIONS,
        apply=True,
    )

    assert infrastructure.commands == [
        ("upgrade", "42d54200970a"),
        ("stamp", "441c04c14c57"),
        ("upgrade", "e4a7b8c9d0e1"),
    ]
    assert report == BootstrapReport(
        masked_cloud_target="db.pr***.supabase.co:5432/postgres",
        initial_state="empty",
        final_state="e4a7b8c9d0e1",
        executed_before_stamp=("5e2716b5ed84", "42d54200970a"),
        stamped_over=("d5338781e8f0", "441c04c14c57"),
        executed_after_stamp=("7b9d2e4f6a81", "c8f1e2a3b4d5", "e4a7b8c9d0e1"),
    )


def test_revision_42_resumes_at_stamp_without_repeating_upgrade() -> None:
    head = _head()
    infrastructure = FakeInfrastructure(
        (
            BootstrapDatabaseState(head, "42d54200970a"),
            BootstrapDatabaseState(head, "441c04c14c57"),
            BootstrapDatabaseState(head, "e4a7b8c9d0e1"),
        )
    )

    run_mobile_poc_bootstrap(
        CONFIG,
        infrastructure,
        versions_directory=VERSIONS,
        apply=True,
    )

    assert infrastructure.commands == [
        ("stamp", "441c04c14c57"),
        ("upgrade", "e4a7b8c9d0e1"),
    ]


def test_physical_mismatch_stops_before_any_alembic_command() -> None:
    damaged = DatabaseSchemaSnapshot(tables=(), sequences=_head().sequences)
    infrastructure = FakeInfrastructure(
        (BootstrapDatabaseState(damaged, "42d54200970a"),)
    )

    with pytest.raises(SchemaConflictError):
        run_mobile_poc_bootstrap(
            CONFIG,
            infrastructure,
            versions_directory=VERSIONS,
            apply=True,
        )

    assert infrastructure.commands == []


def test_local_database_must_be_at_the_approved_head() -> None:
    class WrongLocal(FakeInfrastructure):
        def read_local_state(self) -> BootstrapDatabaseState:
            return BootstrapDatabaseState(_head(), "42d54200970a")

    infrastructure = WrongLocal((BootstrapDatabaseState.empty(),))

    with pytest.raises(SchemaConflictError, match="local"):
        run_mobile_poc_bootstrap(
            CONFIG,
            infrastructure,
            versions_directory=VERSIONS,
            apply=False,
        )

    assert infrastructure.commands == []
