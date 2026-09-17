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

from app.core.config import Settings
from app.domain import Administrator, RealtimeAlert
from app.domain.ppe_management import ActiveOperationSnapshot
from app.ui.alerts import AlertsPage
from app.ui.dashboard.dashboard_page import (
    DashboardPage,
)
from app.ui.employees import EmployeesPage
from app.ui.main.sidebar import Sidebar
from app.ui.operations import OperationsPage
from app.ui.ppe import PpeManagementPage
from app.ui.reports import ReportsPage


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
    realtime_alert_received = Signal(int)
    ppe_snapshot_requested = Signal()
    ppe_session_updated = Signal(object)

    def __init__(self, administrator: Administrator, settings: Settings | None = None) -> None:

        super().__init__()

        self.administrator = administrator
        self._settings = settings or Settings(_env_file=None)

        self.setWindowTitle("2Identify - Sistema de Segurança Industrial")

        self.setMinimumSize(
            1200,
            750,
        )

        self.setStyleSheet(self.estilos())

        self.criar_interface()

    def criar_interface(self) -> None:

        central = QWidget()

        central.setObjectName("central")

        self.setCentralWidget(central)

        layout_principal = QHBoxLayout(central)

        layout_principal.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout_principal.setSpacing(0)

        # ==================================================
        # SIDEBAR
        # ==================================================

        self.sidebar = Sidebar()

        self.sidebar.setFixedWidth(250)

        self.sidebar.pagina_selecionada.connect(self.trocar_pagina)

        layout_principal.addWidget(self.sidebar)

        # ==================================================
        # ÁREA DIREITA
        # ==================================================

        area_direita = QFrame()

        area_direita.setObjectName("area_direita")

        layout_direita = QVBoxLayout(area_direita)

        layout_direita.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout_direita.setSpacing(0)

        # ==================================================
        # HEADER
        # ==================================================

        header = QFrame()

        header.setObjectName("header")

        header.setFixedHeight(72)

        layout_header = QHBoxLayout(header)

        layout_header.setContentsMargins(
            30,
            0,
            30,
            0,
        )

        titulo_header = QLabel("Monitoramento de Segurança")

        titulo_header.setObjectName("header_titulo")

        layout_header.addWidget(titulo_header)

        layout_header.addStretch()

        usuario_nome = QLabel(self.administrator.name)

        usuario_nome.setObjectName("usuario_nome")

        layout_header.addWidget(usuario_nome)

        perfil = QLabel(self.administrator.profile.capitalize())

        perfil.setObjectName("usuario_perfil")

        layout_header.addWidget(perfil)

        layout_direita.addWidget(header)

        # ==================================================
        # STACK DE PÁGINAS
        # ==================================================

        self.stack = QStackedWidget()

        self.stack.setObjectName("conteudo")

        self.dashboard = DashboardPage()

        self.alerts = AlertsPage()
        self.operations = OperationsPage()
        self.ppe_management = PpeManagementPage()
        self.reports = ReportsPage()
        self.employees = EmployeesPage(self._settings)

        self.stack.addWidget(self.dashboard)

        self.stack.addWidget(self.alerts)

        self.stack.addWidget(self.operations)
        self.stack.addWidget(self.ppe_management)
        self.stack.addWidget(self.reports)
        self.stack.addWidget(self.employees)

        layout_direita.addWidget(self.stack)

        layout_principal.addWidget(area_direita)

    # ======================================================
    # NAVEGAÇÃO
    # ======================================================

    def trocar_pagina(
        self,
        pagina: str,
    ) -> None:

        if pagina == "dashboard":
            self.stack.setCurrentWidget(self.dashboard)

        elif pagina == "epis":
            self.stack.setCurrentWidget(self.ppe_management)

        elif pagina == "alertas":
            self.stack.setCurrentWidget(self.alerts)

        elif pagina == "operacoes":
            self.stack.setCurrentWidget(self.operations)

        elif pagina == "relatorios":
            self.stack.setCurrentWidget(self.reports)

        elif pagina == "funcionarios":
            self.stack.setCurrentWidget(self.employees)

        elif pagina == "configuracoes":
            self.mostrar_placeholder("Configurações")

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

        layout = QVBoxLayout(pagina)

        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(titulo)

        label.setObjectName("placeholder")

        layout.addWidget(label)

        self.stack.addWidget(pagina)

        self.stack.setCurrentWidget(pagina)

    def set_realtime_status(self, message: str, *, state: str) -> None:
        self.dashboard.set_realtime_status(message, state=state)
        self.alerts.set_connection_status(message, state=state)
        self.ppe_management.set_connection_status(message, state=state)

    def show_ppe_update(self, snapshot: ActiveOperationSnapshot) -> None:
        self.ppe_management.apply_update(snapshot)
        self.ppe_session_updated.emit(snapshot)

    def show_realtime_alert(self, alert: RealtimeAlert) -> None:
        self.dashboard.show_realtime_alert(alert)
        self.alerts.add_alert(alert)
        self.realtime_alert_received.emit(alert.alert_id)

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

        #dashboard_resumo {
            background-color: #F0F5FF;
            border: 1px solid #D6E4FF;
            border-radius: 10px;
        }

        #dashboard_grafico_painel {
            background-color: white;
            border: 1px solid #E5EAF1;
            border-radius: 14px;
            min-height: 280px;
        }

        #grafico_titulo {
            color: #172033;
            font-size: 15px;
            font-weight: 700;
        }

        #grafico_descricao {
            color: #98A2B3;
            font-size: 11px;
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
            color: #027A48;
            background-color: #ECFDF3;
            border: 1px solid #ABEFC6;
            border-radius: 8px;
            padding: 5px 9px;
            font-size: 14px;
            font-weight: 700;
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

        #alerts_list_panel, #alert_detail_container {
            background-color: white;
            border: 1px solid #E5EAF1;
            border-radius: 12px;
        }

        #alert_detail_scroll {
            background-color: transparent;
        }

        #alert_detail_header {
            background-color: #F8FAFC;
            border: 1px solid #E5EAF1;
            border-radius: 10px;
        }

        #alert_detail_title {
            color: #172033;
            font-size: 22px;
            font-weight: 800;
        }

        #alert_detail_status {
            color: #B54708;
            font-size: 13px;
            font-weight: 700;
        }

        #alert_detail_status[status="encerrado"] {
            color: #667085;
        }

        #alert_detail_status[status="lido"] {
            color: #027A48;
        }

        #alert_detail_summary {
            color: #344054;
            font-size: 14px;
        }

        #alert_detail_section {
            background-color: white;
            border: 1px solid #EAECF0;
            border-radius: 9px;
        }

        #alert_section_title {
            color: #172033;
            font-size: 15px;
            font-weight: 700;
        }

        #alert_detail_key {
            color: #667085;
            font-size: 12px;
            font-weight: 600;
        }

        #alert_detail_value {
            color: #172033;
            font-size: 12px;
        }

        #alert_muted, #alert_detail_placeholder {
            color: #98A2B3;
            font-size: 12px;
        }

        #alerts_feedback {
            background-color: #EFF8FF;
            border: 1px solid #B2DDFF;
            border-radius: 8px;
            color: #175CD3;
            padding: 8px;
        }

        #alerts_feedback[state="error"] {
            background-color: #FEF3F2;
            border-color: #FECDCA;
            color: #B42318;
        }

        #alerts_feedback[state="success"] {
            background-color: #ECFDF3;
            border-color: #ABEFC6;
            color: #027A48;
        }

        #alerts_refresh, #alert_confirm, #alert_close {
            border: none;
            border-radius: 8px;
            padding: 9px 15px;
            font-weight: 700;
        }

        #alerts_refresh, #alert_confirm {
            background-color: #2563EB;
            color: white;
        }

        #alert_close {
            background-color: #B42318;
            color: white;
        }

        #alerts_refresh:disabled, #alert_confirm:disabled, #alert_close:disabled {
            background-color: #D0D5DD;
            color: #667085;
        }

        #placeholder {
            color: #667085;
            font-size: 28px;
            font-weight: 700;
        }

        #operations_page {
            background-color: #F7F9FC;
        }

        #operations_panel {
            background-color: white;
            border: 1px solid #E5EAF1;
            border-radius: 12px;
        }

        #operations_section_title, #risk_editor_title {
            color: #172033;
            font-size: 16px;
            font-weight: 700;
        }

        #operations_feedback {
            background-color: #EFF8FF;
            border: 1px solid #B2DDFF;
            border-radius: 8px;
            color: #175CD3;
            padding: 8px;
        }

        #operations_feedback[state="error"] {
            background-color: #FEF3F2;
            border-color: #FECDCA;
            color: #B42318;
        }

        #operations_feedback[state="success"] {
            background-color: #ECFDF3;
            border-color: #ABEFC6;
            color: #027A48;
        }

        #primary_action {
            background-color: #2563EB;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 10px 16px;
            font-weight: 700;
        }

        #primary_action:disabled {
            background-color: #D0D5DD;
            color: #667085;
        }
        """
