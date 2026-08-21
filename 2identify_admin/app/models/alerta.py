from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Alerta(Base):
    """
    Representa um alerta gerado a partir de uma ocorrência.
    """

    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    ocorrencia_id: Mapped[int] = mapped_column(
        ForeignKey(
            "ocorrencias.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    nivel: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="nao_lido",
    )

    observacao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    recebido_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    encerrado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    encerrado_por: Mapped[int | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    ocorrencia = relationship(
        "Ocorrencia",
        back_populates="alerta",
    )

    usuario_encerramento = relationship(
        "Usuario",
        foreign_keys=[encerrado_por],
    )

    def __repr__(self) -> str:
        return (
            f"<Alerta("
            f"id={self.id}, "
            f"nivel='{self.nivel}', "
            f"status='{self.status}'"
            f")>"
        )