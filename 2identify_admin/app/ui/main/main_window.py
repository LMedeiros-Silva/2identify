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
from app.ui.styles import main_window_stylesheet


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
        return main_window_stylesheet()
