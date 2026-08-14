from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.main.sidebar import Sidebar
from app.ui.dashboard.dashboard_page import (
    DashboardPage,
)


class MainWindow(QMainWindow):
    """
    Janela principal do 2Identify.

    Contém:
        - Sidebar
        - Área de conteúdo
        - Dashboard
        - Usuário logado
    """

    def __init__(self, usuario):

        super().__init__()

        self.usuario = usuario

        self.setWindowTitle(
            "2Identify - Sistema de Segurança Industrial"
        )

        self.setMinimumSize(
            1200,
            750,
        )

        self.setStyleSheet(
            self.estilos()
        )

        self.criar_interface()

    def criar_interface(self):

        central = QWidget()

        central.setObjectName(
            "central"
        )

        self.setCentralWidget(
            central
        )

        layout_principal = QHBoxLayout(
            central
        )

        layout_principal.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout_principal.setSpacing(
            0
        )

        # ==================================================
        # SIDEBAR
        # ==================================================

        self.sidebar = Sidebar()

        self.sidebar.setFixedWidth(
            250
        )

        self.sidebar.pagina_selecionada.connect(
            self.trocar_pagina
        )

        layout_principal.addWidget(
            self.sidebar
        )

        # ==================================================
        # ÁREA DIREITA
        # ==================================================

        area_direita = QFrame()

        area_direita.setObjectName(
            "area_direita"
        )

        layout_direita = QVBoxLayout(
            area_direita
        )

        layout_direita.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout_direita.setSpacing(
            0
        )

        # ==================================================
        # HEADER
        # ==================================================

        header = QFrame()

        header.setObjectName(
            "header"
        )

        header.setFixedHeight(
            72
        )

        layout_header = QHBoxLayout(
            header
        )

        layout_header.setContentsMargins(
            30,
            0,
            30,
            0,
        )

        titulo_header = QLabel(
            "Monitoramento de Segurança"
        )

        titulo_header.setObjectName(
            "header_titulo"
        )

        layout_header.addWidget(
            titulo_header
        )

        layout_header.addStretch()

        usuario_nome = QLabel(
            self.usuario.nome
        )

        usuario_nome.setObjectName(
            "usuario_nome"
        )

        layout_header.addWidget(
            usuario_nome
        )

        perfil = QLabel(
            self.usuario.perfil.capitalize()
        )

        perfil.setObjectName(
            "usuario_perfil"
        )

        layout_header.addWidget(
            perfil
        )

        layout_direita.addWidget(
            header
        )

        # ==================================================
        # STACK DE PÁGINAS
        # ==================================================

        self.stack = QStackedWidget()

        self.stack.setObjectName(
            "conteudo"
        )

        self.dashboard = (
            DashboardPage()
        )

        self.stack.addWidget(
            self.dashboard
        )

        layout_direita.addWidget(
            self.stack
        )

        layout_principal.addWidget(
            area_direita
        )

    # ======================================================
    # NAVEGAÇÃO
    # ======================================================

    def trocar_pagina(
        self,
        pagina,
    ):

        if pagina == "dashboard":

            self.stack.setCurrentWidget(
                self.dashboard
            )

        elif pagina == "epis":

            self.mostrar_placeholder(
                "Gestão de EPIs"
            )

        elif pagina == "alertas":

            self.mostrar_placeholder(
                "Alertas"
            )

        elif pagina == "relatorios":

            self.mostrar_placeholder(
                "Relatórios"
            )

        elif pagina == "configuracoes":

            self.mostrar_placeholder(
                "Configurações"
            )

    # ======================================================
    # PLACEHOLDER TEMPORÁRIO
    # ======================================================

    def mostrar_placeholder(
        self,
        titulo,
    ):

        pagina = QWidget()

        layout = QVBoxLayout(
            pagina
        )

        layout.setAlignment(
            Qt.AlignCenter
        )

        label = QLabel(
            titulo
        )

        label.setObjectName(
            "placeholder"
        )

        layout.addWidget(
            label
        )

        self.stack.addWidget(
            pagina
        )

        self.stack.setCurrentWidget(
            pagina
        )

    # ======================================================
    # ESTILOS
    # ======================================================

    @staticmethod
    def estilos():

        return """
        QMainWindow {
            background-color: #F7F9FC;
        }

        #central {
            background-color: #F7F9FC;
        }

        #sidebar {
            background-color: #0B1F3A;
        }

        #sidebar_logo {
            color: white;
            font-size: 28px;
            font-weight: 800;
        }

        #sidebar_subtitulo {
            color: #8EA4C2;
            font-size: 12px;
        }

        #menu_botao {
            background-color: transparent;
            color: #AFC0D7;
            border: none;
            border-radius: 9px;
            text-align: left;
            padding: 13px 15px;
            font-size: 14px;
            font-weight: 500;
        }

        #menu_botao:hover {
            background-color: #142F52;
            color: white;
        }

        #menu_botao:checked {
            background-color: #2563EB;
            color: white;
            font-weight: 700;
        }

        #area_direita {
            background-color: #F7F9FC;
        }

        #header {
            background-color: white;
            border-bottom: 1px solid #E5EAF1;
        }

        #header_titulo {
            color: #172033;
            font-size: 16px;
            font-weight: 600;
        }

        #usuario_nome {
            color: #172033;
            font-size: 14px;
            font-weight: 600;
            margin-right: 8px;
        }

        #usuario_perfil {
            color: #718096;
            font-size: 12px;
        }

        #dashboard_page {
            background-color: #F7F9FC;
        }

        #pagina_titulo {
            color: #172033;
            font-size: 28px;
            font-weight: 700;
        }

        #pagina_subtitulo {
            color: #718096;
            font-size: 14px;
        }

        #dashboard_card {
            background-color: white;
            border: 1px solid #E5EAF1;
            border-radius: 14px;
        }

        #card_titulo {
            color: #667085;
            font-size: 13px;
            font-weight: 600;
        }

        #card_valor {
            color: #172033;
            font-size: 30px;
            font-weight: 800;
            margin-top: 7px;
        }

        #card_descricao {
            color: #98A2B3;
            font-size: 12px;
            margin-top: 3px;
        }

        #dashboard_painel {
            background-color: white;
            border: 1px solid #E5EAF1;
            border-radius: 14px;
            min-height: 260px;
        }

        #painel_titulo {
            color: #172033;
            font-size: 16px;
            font-weight: 700;
        }

        #painel_texto {
            color: #718096;
            font-size: 13px;
        }

        #indicador_conformidade {
            color: #16A34A;
            font-size: 52px;
            font-weight: 800;
        }

        #sem_alertas {
            color: #98A2B3;
            font-size: 13px;
        }

        #placeholder {
            color: #667085;
            font-size: 28px;
            font-weight: 700;
        }
        """
    