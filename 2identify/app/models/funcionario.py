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


class Funcionario(Base):
    """
    Representa um funcionário monitorado pelo 2Identify.
    """

    __tablename__ = "funcionarios"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    nome: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    matricula: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    cargo: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    turno: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    foto: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    setor_id: Mapped[int] = mapped_column(
        ForeignKey(
            "setores.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    setor = relationship(
        "Setor",
        back_populates="funcionarios",
    )

    epis = relationship(
        "FuncionarioEPI",
        back_populates="funcionario",
        cascade="all, delete-orphan",
    )

    ocorrencias = relationship(
        "Ocorrencia",
        back_populates="funcionario",
    )

    def __repr__(self) -> str:
        return (
            f"<Funcionario("
            f"id={self.id}, "
            f"nome='{self.nome}', "
            f"matricula='{self.matricula}'"
            f")>"
        )