from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FuncionarioEPI(Base):
    """
    Relaciona um funcionário aos EPIs obrigatórios
    para sua atividade.
    """

    __tablename__ = "funcionario_epis"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    funcionario_id: Mapped[int] = mapped_column(
        ForeignKey(
            "funcionarios.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    epi_id: Mapped[int] = mapped_column(
        ForeignKey(
            "epis.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    obrigatorio: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    entregue: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    funcionario = relationship(
        "Funcionario",
        back_populates="epis",
    )

    epi = relationship(
        "EPI",
        back_populates="funcionarios",
    )

    def __repr__(self) -> str:
        return (
            f"<FuncionarioEPI("
            f"funcionario_id={self.funcionario_id}, "
            f"epi_id={self.epi_id}"
            f")>"
        )