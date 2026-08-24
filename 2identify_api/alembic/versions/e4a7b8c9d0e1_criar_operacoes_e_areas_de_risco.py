"""Criar operacoes, EPIs obrigatorios e areas de risco

Revision ID: e4a7b8c9d0e1
Revises: c8f1e2a3b4d5
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "c8f1e2a3b4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "areas_risco",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("geometria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_id", "nome", name="uq_areas_risco_camera_nome"),
    )
    op.create_index("ix_areas_risco_camera_ativa", "areas_risco", ["camera_id", "ativa"])

    op.create_table(
        "operacoes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("descricao", sa.String(length=500), nullable=True),
        sa.Column("area_risco_id", sa.Integer(), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["area_risco_id"], ["areas_risco.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome", name="uq_operacoes_nome"),
    )
    op.create_index("ix_operacoes_ativa_nome", "operacoes", ["ativa", "nome"])

    op.create_table(
        "operacao_epis",
        sa.Column("operacao_id", sa.Integer(), nullable=False),
        sa.Column("epi_id", sa.Integer(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["epi_id"], ["epis.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["operacao_id"], ["operacoes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("operacao_id", "epi_id"),
    )
    op.create_index("ix_operacao_epis_epi_id", "operacao_epis", ["epi_id"])


def downgrade() -> None:
    op.drop_index("ix_operacao_epis_epi_id", table_name="operacao_epis")
    op.drop_table("operacao_epis")
    op.drop_index("ix_operacoes_ativa_nome", table_name="operacoes")
    op.drop_table("operacoes")
    op.drop_index("ix_areas_risco_camera_ativa", table_name="areas_risco")
    op.drop_table("areas_risco")
