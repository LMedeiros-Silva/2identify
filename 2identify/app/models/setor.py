from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Setor(Base):
    """
    Representa uma área/setor operacional da empresa.
    """

    __tablename__ = "setores"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    nome: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    descricao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    funcionarios = relationship(
        "Funcionario",
        back_populates="setor",
    )

    def __repr__(self) -> str:
        return (
            f"<Setor("
            f"id={self.id}, "
            f"nome='{self.nome}'"
            f")>"
        )