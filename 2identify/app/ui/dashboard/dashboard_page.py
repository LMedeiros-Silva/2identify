from app.core.database import SessionLocal
from app.services.dashboard_service import DashboardService
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class DashboardPage(QWidget):
    """
    Dashboard principal do 2Identify.
    """

    def __init__(self):
        super().__init__()

        self.setObjectName(
            "dashboard_page"
        )

        self.criar_interface()

        self.carregar_dados()

    def criar_interface(self):

        layout_principal = QVBoxLayout(
            self
        )

        layout_principal.setContentsMargins(
            35,
            30,
            35,
            30,
        )

        layout_principal.setSpacing(
            25
        )

        # ==================================================
        # CABEÇALHO
        # ==================================================

        titulo = QLabel(
            "Dashboard"
        )

        titulo.setObjectName(
            "pagina_titulo"
        )

        layout_principal.addWidget(
            titulo
        )

        subtitulo = QLabel(
            "Visão geral da segurança operacional"
        )

        subtitulo.setObjectName(
            "pagina_subtitulo"
        )

        layout_principal.addWidget(
            subtitulo
        )

        # ==================================================
        # CARDS
        # ==================================================

        cards_layout = QGridLayout()

        cards_layout.setSpacing(
            18
        )

        self.card_funcionarios = (
            self.criar_card(
                "Funcionários",
                "0",
                "Funcionários cadastrados",
            )
        )

        self.card_conformidade = (
            self.criar_card(
                "Conformidade",
                "100%",
                "EPIs em conformidade",
            )
        )

        self.card_alertas = (
            self.criar_card(
                "Alertas",
                "0",
                "Alertas registrados",
            )
        )

        self.card_criticos = (
            self.criar_card(
                "Críticos",
                "0",
                "Alertas críticos",
            )
        )

        cards_layout.addWidget(
            self.card_funcionarios,
            0,
            0,
        )

        cards_layout.addWidget(
            self.card_conformidade,
            0,
            1,
        )

        cards_layout.addWidget(
            self.card_alertas,
            0,
            2,
        )

        cards_layout.addWidget(
            self.card_criticos,
            0,
            3,
        )

        layout_principal.addLayout(
            cards_layout
        )

        # ==================================================
        # PARTE INFERIOR
        # ==================================================

        conteudo = QHBoxLayout()

        conteudo.setSpacing(
            20
        )

        # -----------------------------------------------
        # CONFORMIDADE
        # -----------------------------------------------

        painel_conformidade = QFrame()

        painel_conformidade.setObjectName(
            "dashboard_painel"
        )

        layout_conformidade = QVBoxLayout(
            painel_conformidade
        )

        titulo_conformidade = QLabel(
            "Conformidade de EPIs"
        )

        titulo_conformidade.setObjectName(
            "painel_titulo"
        )

        layout_conformidade.addWidget(
            titulo_conformidade
        )

        texto_conformidade = QLabel(
            "Todos os funcionários cadastrados "
            "estão com seus EPIs obrigatórios."
        )

        texto_conformidade.setObjectName(
            "painel_texto"
        )

        texto_conformidade.setWordWrap(
            True
        )

        layout_conformidade.addWidget(
            texto_conformidade
        )

        layout_conformidade.addStretch()

        indicador = QLabel(
            "100%"
        )

        indicador.setObjectName(
            "indicador_conformidade"
        )

        indicador.setAlignment(
            Qt.AlignCenter
        )

        layout_conformidade.addWidget(
            indicador
        )

        legenda = QLabel(
            "Índice geral de conformidade"
        )

        legenda.setObjectName(
            "painel_texto"
        )

        legenda.setAlignment(
            Qt.AlignCenter
        )

        layout_conformidade.addWidget(
            legenda
        )

        conteudo.addWidget(
            painel_conformidade,
            2,
        )

        # -----------------------------------------------
        # ALERTAS RECENTES
        # -----------------------------------------------

        painel_alertas = QFrame()

        painel_alertas.setObjectName(
            "dashboard_painel"
        )

        layout_alertas = QVBoxLayout(
            painel_alertas
        )

        titulo_alertas = QLabel(
            "Alertas recentes"
        )

        titulo_alertas.setObjectName(
            "painel_titulo"
        )

        layout_alertas.addWidget(
            titulo_alertas
        )

        texto_alertas = QLabel(
            "Nenhum alerta registrado."
        )

        texto_alertas.setObjectName(
            "sem_alertas"
        )

        texto_alertas.setAlignment(
            Qt.AlignCenter
        )

        layout_alertas.addWidget(
            texto_alertas
        )

        conteudo.addWidget(
            painel_alertas,
            1,
        )

        layout_principal.addLayout(
            conteudo
        )

        layout_principal.addStretch()

    # ======================================================
    # CARD
    # ======================================================

    def criar_card(
        self,
        titulo,
        valor,
        descricao,
    ):

        card = QFrame()

        card.setObjectName(
            "dashboard_card"
        )

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            22,
            20,
            22,
            20,
        )

        titulo_label = QLabel(
            titulo
        )

        titulo_label.setObjectName(
            "card_titulo"
        )

        layout.addWidget(
            titulo_label
        )

        valor_label = QLabel(
            valor
        )

        valor_label.setObjectName(
            "card_valor"
        )

        layout.addWidget(
            valor_label
        )

        descricao_label = QLabel(
            descricao
        )

        descricao_label.setObjectName(
            "card_descricao"
        )

        layout.addWidget(
            descricao_label
        )

        # Guardamos a referência do label
        # para podermos atualizar o valor posteriormente.

        card.valor_label = valor_label

        return card

    def carregar_dados(self):
        """
        Busca os indicadores diretamente do PostgreSQL.
        """

        session = SessionLocal()

        try:

            service = DashboardService(
                session
            )

            indicadores = (
                service.obter_indicadores()
            )

            # ------------------------------------------
            # FUNCIONÁRIOS
            # ------------------------------------------

            self.card_funcionarios.valor_label.setText(
                str(
                    indicadores["funcionarios"]
                )
            )

            # ------------------------------------------
            # CONFORMIDADE
            # ------------------------------------------

            self.card_conformidade.valor_label.setText(
                f'{indicadores["conformidade"]}%'
            )

            # ------------------------------------------
            # ALERTAS
            # ------------------------------------------

            self.card_alertas.valor_label.setText(
                str(
                    indicadores["alertas"]
                )
            )

            # ------------------------------------------
            # CRÍTICOS
            # ------------------------------------------

            self.card_criticos.valor_label.setText(
                str(
                    indicadores["criticos"]
                )
            )

        except Exception as erro:

            print(
                "Erro ao carregar Dashboard:",
                erro,
            )

        finally:

            session.close()