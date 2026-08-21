from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EPI(Base):
    """
    Representa um equipamento de proteção individual.
    """

    __tablename__ = "epis"

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

    codigo: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
    )

    descricao: Mapped[str | None] = mapped_column(
        String(500),
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
        "FuncionarioEPI",
        back_populates="epi",
    )

    def __repr__(self) -> str:
        return (
            f"<EPI("
            f"id={self.id}, "
            f"nome='{self.nome}'"
            f")>"
        )