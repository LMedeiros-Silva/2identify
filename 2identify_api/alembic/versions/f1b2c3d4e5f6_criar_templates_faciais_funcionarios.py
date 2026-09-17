"""Criar armazenamento central de templates faciais de funcionários.

Revision ID: f1b2c3d4e5f6
Revises: e4a7b8c9d0e1
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e4a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "funcionario_face_templates",
        sa.Column("funcionario_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=80), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["funcionario_id"], ["funcionarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("funcionario_id"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "GRANT SELECT, INSERT, UPDATE ON funcionario_face_templates TO identify_user"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade bloqueado: não apagar templates biométricos cadastrados."
    )
