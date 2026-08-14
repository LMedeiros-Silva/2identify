from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.funcionario import Funcionario
from app.models.funcionario_epi import FuncionarioEPI
from app.models.alerta import Alerta


class DashboardService:
    """
    Serviço responsável por buscar os indicadores
    exibidos no Dashboard.

    A interface não consulta o banco diretamente.
    Ela chama este serviço.
    """

    def __init__(self, session: Session):
        self.session = session

    # ==========================================================
    # FUNCIONÁRIOS
    # ==========================================================

    def total_funcionarios(self) -> int:
        """
        Retorna a quantidade de funcionários ativos.
        """

        resultado = self.session.scalar(
            select(
                func.count(Funcionario.id)
            ).where(
                Funcionario.ativo.is_(True)
            )
        )

        return resultado or 0

    # ==========================================================
    # EPIs
    # ==========================================================

    def total_associacoes_epi(self) -> int:
        """
        Retorna a quantidade de EPIs associados
        aos funcionários.
        """

        resultado = self.session.scalar(
            select(
                func.count(FuncionarioEPI.id)
            )
        )

        return resultado or 0

    # ==========================================================
    # EPIs ENTREGUES
    # ==========================================================

    def total_epis_entregues(self) -> int:
        """
        Retorna quantos EPIs estão marcados como entregues.
        """

        resultado = self.session.scalar(
            select(
                func.count(FuncionarioEPI.id)
            ).where(
                FuncionarioEPI.entregue.is_(True)
            )
        )

        return resultado or 0

    # ==========================================================
    # CONFORMIDADE
    # ==========================================================

    def percentual_conformidade(self) -> float:
        """
        Calcula o percentual geral de EPIs entregues.

        Fórmula:

            entregues / total * 100
        """

        total = self.total_associacoes_epi()

        if total == 0:
            return 0.0

        entregues = self.total_epis_entregues()

        percentual = (
            entregues / total
        ) * 100

        return round(
            percentual,
            1,
        )

    # ==========================================================
    # ALERTAS
    # ==========================================================

    def total_alertas(self) -> int:
        """
        Retorna a quantidade total de alertas.
        """

        resultado = self.session.scalar(
            select(
                func.count(Alerta.id)
            )
        )

        return resultado or 0

    # ==========================================================
    # ALERTAS CRÍTICOS
    # ==========================================================

    def total_alertas_criticos(self) -> int:
        """
        Retorna a quantidade de alertas críticos.
        """

        resultado = self.session.scalar(
            select(
                func.count(Alerta.id)
            ).where(
                Alerta.nivel == "critico"
            )
        )

        return resultado or 0

    # ==========================================================
    # TODOS OS INDICADORES
    # ==========================================================

    def obter_indicadores(self) -> dict:
        """
        Retorna todos os indicadores do Dashboard
        em um único objeto.
        """

        return {
            "funcionarios": self.total_funcionarios(),
            "conformidade": self.percentual_conformidade(),
            "alertas": self.total_alertas(),
            "criticos": self.total_alertas_criticos(),
        }
    