"""Tests for the static Alembic upgrade audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.mobile_poc.migrations import (
    MigrationAuditError,
    audit_migration_upgrade,
    audit_post_stamp_migrations,
)

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def test_real_post_stamp_migrations_are_safe_and_in_exact_order() -> None:
    revisions = audit_post_stamp_migrations(VERSIONS)

    assert revisions == (
        "7b9d2e4f6a81",
        "c8f1e2a3b4d5",
        "e4a7b8c9d0e1",
    )


def test_known_destructive_intermediate_upgrade_is_rejected() -> None:
    migration = VERSIONS / "d5338781e8f0_criar_tabela_de_usuarios.py"

    with pytest.raises(MigrationAuditError, match="d5338781e8f0"):
        audit_migration_upgrade(migration)


@pytest.mark.parametrize(
    "body",
    [
        "op.drop_table('usuarios')",
        "op.alter_column('usuarios', 'id', type_=sa.String())",
        "op.execute('TRUNCATE TABLE usuarios')",
        "op.execute(sa.text('DELETE FROM usuarios'))",
    ],
)
def test_destructive_upgrade_variants_are_rejected(tmp_path: Path, body: str) -> None:
    migration = tmp_path / "unsafe.py"
    migration.write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "revision = 'unsafe'\n"
        "down_revision = '441c04c14c57'\n"
        "def upgrade():\n"
        f"    {body}\n",
        encoding="utf-8",
    )

    with pytest.raises(MigrationAuditError):
        audit_migration_upgrade(migration)
