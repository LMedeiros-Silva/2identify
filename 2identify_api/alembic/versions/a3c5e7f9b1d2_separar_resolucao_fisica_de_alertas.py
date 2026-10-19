"""Separar resolução física do encerramento administrativo de alertas

Revision ID: a3c5e7f9b1d2
Revises: f1b2c3d4e5f6
Create Date: 2026-10-19

A condição física (risco presente no chão de fábrica) passa a ter o próprio
ciclo em ``alertas_ingestao.condicao_resolvida_em``. O ``alertas.status``
continua sendo somente a revisão do Admin (nao_lido → lido → encerrado).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d2"
down_revision: str | Sequence[str] | None = "f1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alertas_ingestao",
        sa.Column("condicao_resolvida_em", sa.DateTime(timezone=True), nullable=True),
    )
    # Before this revision the physical state was not recorded separately. Existing
    # conditions are treated as resolved so that old alerts never keep the tower
    # RED/YELLOW; the Admin history (alertas.status, encerrado_*) is not touched.
    op.execute(
        """
        UPDATE alertas_ingestao
        SET condicao_resolvida_em = COALESCE(
            (SELECT alertas.encerrado_em FROM alertas WHERE alertas.id = alertas_ingestao.alerta_id),
            CURRENT_TIMESTAMP
        )
        """
    )
    op.create_index(
        "ix_alertas_ingestao_condicao_ativa",
        "alertas_ingestao",
        ["operador_usuario_id", "sessao_trabalho_id"],
        unique=False,
        postgresql_where=sa.text("condicao_resolvida_em IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_alertas_ingestao_condicao_ativa", table_name="alertas_ingestao")
    op.drop_column("alertas_ingestao", "condicao_resolvida_em")
