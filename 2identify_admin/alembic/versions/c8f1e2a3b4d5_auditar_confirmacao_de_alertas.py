"""Auditar confirmação de alertas

Revision ID: c8f1e2a3b4d5
Revises: 7b9d2e4f6a81
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8f1e2a3b4d5"
down_revision: str | Sequence[str] | None = "7b9d2e4f6a81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alertas",
        sa.Column("confirmado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alertas",
        sa.Column("confirmado_por", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_alertas_confirmado_por_usuarios",
        "alertas",
        "usuarios",
        ["confirmado_por"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_alertas_status_criado_em",
        "alertas",
        ["status", "criado_em"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alertas_status_criado_em", table_name="alertas")
    op.drop_constraint(
        "fk_alertas_confirmado_por_usuarios",
        "alertas",
        type_="foreignkey",
    )
    op.drop_column("alertas", "confirmado_por")
    op.drop_column("alertas", "confirmado_em")
