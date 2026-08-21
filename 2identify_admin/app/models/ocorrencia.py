from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Ocorrencia(Base):
    """
    Representa uma ocorrência detectada pelo sistema.
    """

    __tablename__ = "ocorrencias"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    funcionario_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "funcionarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    camera_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "cameras.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    tipo: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    descricao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confianca: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    imagem: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    video: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    detectado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    funcionario = relationship(
        "Funcionario",
        back_populates="ocorrencias",
    )

    camera = relationship(
        "Camera",
        back_populates="ocorrencias",
    )

    alerta = relationship(
        "Alerta",
        back_populates="ocorrencia",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Ocorrencia("
            f"id={self.id}, "
            f"tipo='{self.tipo}'"
            f")>"
        )