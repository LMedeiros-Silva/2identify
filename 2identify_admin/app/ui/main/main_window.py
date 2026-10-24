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
from app.ui.settings import SettingsPage
from app.ui.styles import main_window_stylesheet

_PAGE_SUBTITLES = {
    "dashboard": "Operações, alertas e indicadores da planta",
    "epis": "Última observação enviada por cada estação Operator",
    "alertas": "Confirme os alertas recebidos e encerre os tratados",
    "operacoes": "Operações, câmeras e áreas de risco",
    "relatorios": "Exporte alertas e ocorrências em Excel",
    "funcionarios": "Cadastro, EPIs e Face ID",
    "configuracoes": "Conexões e sessão deste Admin",
}

_PAGE_TITLES = {
    "dashboard": "Central de segurança",
    "epis": "Gestão de EPIs",
    "alertas": "Alertas",
    "operacoes": "Operações e áreas",
    "relatorios": "Relatórios",
    "funcionarios": "Funcionários",
    "configuracoes": "Configurações",
}


def _initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    if not parts:
        return "?"
    letters = parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")
    return letters.upper()


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

        self.sidebar.setFixedWidth(236)

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

        header.setFixedHeight(64)

        layout_header = QHBoxLayout(header)

        layout_header.setContentsMargins(
            28,
            0,
            24,
            0,
        )

        layout_header.setSpacing(12)

        self.titulo_header = QLabel(_PAGE_TITLES["dashboard"])

        self.titulo_header.setObjectName("header_titulo")

        layout_header.addWidget(self.titulo_header, 0, Qt.AlignmentFlag.AlignVCenter)

        self.subtitulo_header = QLabel(_PAGE_SUBTITLES["dashboard"])
        self.subtitulo_header.setObjectName("header_contexto")
        layout_header.addSpacing(4)
        layout_header.addWidget(self.subtitulo_header, 0, Qt.AlignmentFlag.AlignVCenter)

        layout_header.addStretch()

        self.header_conexao = QLabel("● Tempo real desconectado")
        self.header_conexao.setObjectName("header_conexao")
        self.header_conexao.setProperty("state", "offline")
        layout_header.addWidget(self.header_conexao, 0, Qt.AlignmentFlag.AlignVCenter)

        divisor = QFrame()
        divisor.setObjectName("header_divisor")
        divisor.setFixedSize(1, 30)
        layout_header.addSpacing(6)
        layout_header.addWidget(divisor)
        layout_header.addSpacing(6)

        avatar = QLabel(_initials(self.administrator.name))
        avatar.setObjectName("usuario_avatar")
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_header.addWidget(avatar)

        identificacao = QVBoxLayout()
        identificacao.setSpacing(0)
        identificacao.addStretch()

        usuario_nome = QLabel(self.administrator.name)

        usuario_nome.setObjectName("usuario_nome")

        identificacao.addWidget(usuario_nome)

        perfil = QLabel(self.administrator.profile.capitalize())

        perfil.setObjectName("usuario_perfil")

        identificacao.addWidget(perfil)
        identificacao.addStretch()

        layout_header.addLayout(identificacao)

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
        self.settings_page = SettingsPage(
            str(self._settings.api_url),
            self.administrator.name,
            self.administrator.username,
            self.administrator.profile,
        )
        self.settings_page.test_requested.connect(self.dashboard.refresh_requested.emit)
        self.settings_page.logout_requested.connect(lambda: self.sidebar.selecionar("sair"))
        self.dashboard.api_status_changed.connect(self._update_api_status)


        self.stack.addWidget(self.dashboard)

        self.dashboard.navigate_requested.connect(self.sidebar.selecionar)
        self.dashboard.alert_open_requested.connect(self.abrir_alerta)
        self.dashboard.open_alerts_changed.connect(
            lambda quantidade: self.sidebar.set_badge("alertas", quantidade)
        )
        self.alerts.alerts_changed.connect(self.dashboard.set_recent_alerts)
        self.ppe_management.active_operations_changed.connect(
            self.dashboard.set_active_operations
        )

        self.stack.addWidget(self.alerts)
        self.operations.catalog_changed.connect(self._update_report_catalog)
        self.employees.directory_changed.connect(self._update_report_directory)

        self.stack.addWidget(self.operations)
        self.stack.addWidget(self.ppe_management)
        self.stack.addWidget(self.reports)
        self.stack.addWidget(self.employees)
        self.stack.addWidget(self.settings_page)

        layout_direita.addWidget(self.stack)

        layout_principal.addWidget(area_direita)

    # ======================================================
    # NAVEGAÇÃO
    # ======================================================

    def trocar_pagina(
        self,
        pagina: str,
    ) -> None:

        if pagina in _PAGE_TITLES:
            self.titulo_header.setText(_PAGE_TITLES[pagina])
            self.subtitulo_header.setText(_PAGE_SUBTITLES[pagina])

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
            self.stack.setCurrentWidget(self.settings_page)

        elif pagina == "sair":
            self.logout_requested.emit()

    def _update_report_catalog(self, operations: object, cameras: object) -> None:
        self.reports.set_operations(operations)  # type: ignore[arg-type]
        self.reports.set_cameras(cameras)  # type: ignore[arg-type]

    def _update_report_directory(self, employees: object, sectors: object) -> None:
        self.reports.set_employees(employees)  # type: ignore[arg-type]
        self.reports.set_sectors(sectors)  # type: ignore[arg-type]

    def _update_api_status(self, generated_at: object, message: str) -> None:
        if generated_at is None:
            self.settings_page.show_api_error(message)
        else:
            self.settings_page.show_api_ok(generated_at)  # type: ignore[arg-type]

    def abrir_alerta(self, alert_id: int) -> None:
        self.sidebar.selecionar("alertas")
        self.alerts.select_alert(alert_id)

    def set_realtime_status(self, message: str, *, state: str) -> None:
        self.header_conexao.setText(
            {
                "connected": "● Tempo real conectado",
                "connecting": "● Conectando ao tempo real",
            }.get(state, "● Tempo real offline")
        )
        self.header_conexao.setToolTip(message)
        self.header_conexao.setProperty("state", state)
        self.header_conexao.style().unpolish(self.header_conexao)
        self.header_conexao.style().polish(self.header_conexao)
        self.dashboard.set_realtime_status(message, state=state)
        self.alerts.set_connection_status(message, state=state)
        self.ppe_management.set_connection_status(message, state=state)
        self.settings_page.set_realtime_status(message, state=state)

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
