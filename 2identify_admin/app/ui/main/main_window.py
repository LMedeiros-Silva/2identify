from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain import Administrator, RealtimeAlert
from app.ui.alerts import AlertsPage
from app.ui.dashboard.dashboard_page import (
    DashboardPage,
)
from app.ui.main.sidebar import Sidebar


class MainWindow(QMainWindow):
    """
    Janela principal do 2Identify.

    Contém:
        - Sidebar
        - Área de conteúdo
        - Dashboard
        - Usuário logado
    """

    logout_requested = Signal()

    def __init__(self, administrator: Administrator) -> None:

        super().__init__()

        self.administrator = administrator

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

    def criar_interface(self) -> None:

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
            self.administrator.name
        )

        usuario_nome.setObjectName(
            "usuario_nome"
        )

        layout_header.addWidget(
            usuario_nome
        )

        perfil = QLabel(
            self.administrator.profile.capitalize()
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

        self.alerts = AlertsPage()

        self.stack.addWidget(
            self.dashboard
        )

        self.stack.addWidget(
            self.alerts
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
        pagina: str,
    ) -> None:

        if pagina == "dashboard":

            self.stack.setCurrentWidget(
                self.dashboard
            )

        elif pagina == "epis":

            self.mostrar_placeholder(
                "Gestão de EPIs"
            )

        elif pagina == "alertas":

            self.stack.setCurrentWidget(
                self.alerts
            )

        elif pagina == "relatorios":

            self.mostrar_placeholder(
                "Relatórios"
            )

        elif pagina == "configuracoes":

            self.mostrar_placeholder(
                "Configurações"
            )

        elif pagina == "sair":

            self.logout_requested.emit()

    # ======================================================
    # PLACEHOLDER TEMPORÁRIO
    # ======================================================

    def mostrar_placeholder(
        self,
        titulo: str,
    ) -> None:

        pagina = QWidget()

        layout = QVBoxLayout(
            pagina
        )

        layout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
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

    def set_realtime_status(self, message: str, *, state: str) -> None:
        self.dashboard.set_realtime_status(message, state=state)
        self.alerts.set_connection_status(message, state=state)

    def show_realtime_alert(self, alert: RealtimeAlert) -> None:
        self.dashboard.show_realtime_alert(alert)
        self.alerts.add_alert(alert)

    # ======================================================
    # ESTILOS
    # ======================================================

    @staticmethod
    def estilos() -> str:

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

        #dashboard_status {
            color: #667085;
            font-size: 13px;
        }

        #dashboard_status[state="error"] {
            color: #B42318;
        }

        #dashboard_status[state="ready"] {
            color: #027A48;
        }

        #realtime_status {
            color: #667085;
            font-size: 12px;
        }

        #realtime_status[state="connected"] {
            color: #027A48;
        }

        #realtime_status[state="offline"] {
            color: #B54708;
        }

        #realtime_alert_banner {
            background-color: #FFF4E5;
            border: 1px solid #FDB022;
            border-radius: 8px;
            color: #7A2E0E;
            padding: 10px;
        }

        #realtime_alert_banner[severity="critical"] {
            background-color: #FEF3F2;
            border-color: #F04438;
            color: #912018;
        }

        #dashboard_retry {
            background-color: #2563EB;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 14px;
            font-weight: 600;
        }

        #dashboard_retry:hover {
            background-color: #1D4ED8;
        }

        #dashboard_retry:disabled {
            background-color: #93B4F4;
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

        #alerts_page {
            background-color: #F7F9FC;
        }

        #alert_banner {
            background-color: #FFF4E5;
            border: 1px solid #FDB022;
            border-radius: 10px;
        }

        #alert_banner[severity="critical"] {
            background-color: #FEF3F2;
            border-color: #F04438;
        }

        #alert_banner_text {
            color: #7A2E0E;
            font-weight: 600;
        }

        #alert_list {
            background-color: white;
            border: 1px solid #E5EAF1;
            border-radius: 10px;
            color: #172033;
            padding: 8px;
        }

        #placeholder {
            color: #667085;
            font-size: 28px;
            font-weight: 700;
        }
        """
    
