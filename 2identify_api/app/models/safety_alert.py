"""Owned ingestion mapping and SQL views of existing Admin-owned alert tables."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, column, table
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

SAFETY_OCCURRENCES = table(
    "ocorrencias",
    column("id", Integer),
    column("funcionario_id", Integer),
    column("camera_id", Integer),
    column("tipo", String(100)),
    column("descricao", String),
    column("confianca"),
    column("imagem", String(500)),
    column("video", String(500)),
    column("detectado_em", DateTime(timezone=True)),
)

PERSISTED_SAFETY_ALERTS = table(
    "alertas",
    column("id", Integer),
    column("ocorrencia_id", Integer),
    column("nivel", String(30)),
    column("status", String(30)),
    column("observacao", String),
    column("criado_em", DateTime(timezone=True)),
    column("recebido_em", DateTime(timezone=True)),
    column("confirmado_em", DateTime(timezone=True)),
    column("confirmado_por", Integer),
    column("encerrado_em", DateTime(timezone=True)),
    column("encerrado_por", Integer),
)

SAFETY_EMPLOYEES = table(
    "funcionarios",
    column("id", Integer),
    column("nome", String(150)),
    column("matricula", String(50)),
    column("cargo", String(100)),
    column("turno", String(50)),
    column("setor_id", Integer),
)

SAFETY_CAMERAS = table(
    "cameras",
    column("id", Integer),
    column("nome", String(100)),
    column("descricao", String(255)),
    column("setor_id", Integer),
)

SAFETY_SECTORS = table(
    "setores",
    column("id", Integer),
    column("nome", String(100)),
)


class SafetyAlertIngestion(Base):
    """Idempotency and operational context owned by the API migration."""

    __tablename__ = "alertas_ingestao"

    evento_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    alerta_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    sessao_trabalho_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operador_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    operacao_id: Mapped[int] = mapped_column(Integer, nullable=False)
    area_risco_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    violacao_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    assunto_chave: Mapped[str] = mapped_column(String(150), nullable=False)
    recebido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
