"""Adicionar ingestão idempotente de alertas

Revision ID: 7b9d2e4f6a81
Revises: 441c04c14c57
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7b9d2e4f6a81"
down_revision: str | Sequence[str] | None = "441c04c14c57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alertas_ingestao",
        sa.Column("evento_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("alerta_id", sa.Integer(), nullable=False),
        sa.Column(
            "sessao_trabalho_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("operador_usuario_id", sa.Integer(), nullable=True),
        sa.Column("operacao_id", sa.Integer(), nullable=False),
        sa.Column("area_risco_id", sa.Integer(), nullable=True),
        sa.Column("violacao_tipo", sa.String(length=50), nullable=False),
        sa.Column("assunto_chave", sa.String(length=150), nullable=False),
        sa.Column("recebido_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["alerta_id"],
            ["alertas.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["operador_usuario_id"],
            ["usuarios.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("evento_id"),
        sa.UniqueConstraint("alerta_id"),
    )
    op.create_index(
        "ix_alertas_ingestao_operador_usuario_id",
        "alertas_ingestao",
        ["operador_usuario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_alertas_ingestao_operador_usuario_id",
        table_name="alertas_ingestao",
    )
    op.drop_table("alertas_ingestao")
