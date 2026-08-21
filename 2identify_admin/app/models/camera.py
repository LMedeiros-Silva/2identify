from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Camera(Base):
    """
    Representa uma câmera utilizada pelo sistema.
    """

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    nome: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    descricao: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    endereco: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    setor_id: Mapped[int] = mapped_column(
        ForeignKey(
            "setores.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    ativa: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    ocorrencias = relationship(
        "Ocorrencia",
        back_populates="camera",
    )

    def __repr__(self) -> str:
        return (
            f"<Camera("
            f"id={self.id}, "
            f"nome='{self.nome}'"
            f")>"
        )