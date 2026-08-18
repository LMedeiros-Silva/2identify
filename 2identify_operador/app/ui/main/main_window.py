"""Main authenticated window for 2Identify Operator."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import Operation, WorkSession
from app.ui.active import ActiveOperationPage
from app.ui.components.sidebar import WORKS_ROUTE, Sidebar
from app.ui.operations import OperationsPage
from app.ui.safety import SafetyVerificationPage

_AUTHENTICATION_LABELS = {
    AuthenticationMethod.FACE_ID: "Face ID",
    AuthenticationMethod.CREDENTIALS: "Credenciais",
}


class MainWindow(QMainWindow):
    """Top-level shell shown only after an authenticated session exists."""

    logout_requested = Signal()

    def __init__(self, session: OperatorSession, app_version: str) -> None:
        super().__init__()
        self._session = session
        self._app_version = app_version

        self.setObjectName("mainWindow")
        self.setWindowTitle("2Identify Operator")
        self.setMinimumSize(1024, 640)
        self.resize(1440, 900)
        self.setCentralWidget(self._build_root())

    @property
    def session(self) -> OperatorSession:
        """Expose the immutable session snapshot to authenticated pages."""

        return self._session

    @property
    def operations_page(self) -> OperationsPage:
        """Expose the operations presentation page to its future controller."""

        return self._operations_page

    @property
    def safety_verification_page(self) -> SafetyVerificationPage:
        """Expose the safety preparation page within the authenticated shell."""

        return self._safety_verification_page

    @property
    def active_operation_page(self) -> ActiveOperationPage:
        """Expose the active local work-session presentation."""

        return self._active_operation_page

    def _build_root(self) -> QWidget:
        root = QWidget()
        root.setObjectName("mainRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = Sidebar(self._app_version)
        self._sidebar.route_requested.connect(self._handle_route_request)
        self._sidebar.logout_requested.connect(self.logout_requested)
        layout.addWidget(self._sidebar)

        workspace = QWidget()
        workspace.setObjectName("mainWorkspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self._build_header())

        self._page_stack = QStackedWidget()
        self._page_stack.setObjectName("mainPageStack")
        self._operations_page = OperationsPage()
        self._page_stack.addWidget(self._operations_page)
        self._safety_verification_page = SafetyVerificationPage(self._session)
        self._safety_verification_page.back_requested.connect(self.show_operations)
        self._page_stack.addWidget(self._safety_verification_page)
        self._active_operation_page = ActiveOperationPage(self._session)
        self._page_stack.addWidget(self._active_operation_page)
        workspace_layout.addWidget(self._page_stack, 1)
        layout.addWidget(workspace, 1)
        return root

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("mainHeader")
        header.setFixedHeight(76)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 0, 28, 0)
        layout.setSpacing(14)

        page_context = QVBoxLayout()
        page_context.setSpacing(1)
        self._page_title = self._label("Trabalhos", "mainPageTitle")
        page_context.addWidget(self._page_title)
        self._page_context = self._label(
            "Ambiente do operador",
            "mainPageContext",
        )
        page_context.addWidget(self._page_context)
        layout.addLayout(page_context)
        layout.addStretch(1)

        session_status = self._label("SESSÃO ATIVA", "mainSessionBadge")
        session_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        session_status.setFixedHeight(26)
        layout.addWidget(session_status)

        operator = QVBoxLayout()
        operator.setSpacing(1)
        operator_name = self._label(self._session.operator_name, "mainOperatorName")
        operator_name.setAlignment(Qt.AlignmentFlag.AlignRight)
        operator.addWidget(operator_name)
        authentication = _AUTHENTICATION_LABELS[self._session.authentication_method]
        operator_detail = self._label(
            f"Operador #{self._session.operator_id} · {authentication}",
            "mainOperatorDetail",
        )
        operator_detail.setAlignment(Qt.AlignmentFlag.AlignRight)
        operator.addWidget(operator_detail)
        layout.addLayout(operator)
        return header

    @Slot(str)
    def _handle_route_request(self, route: str) -> None:
        if route == WORKS_ROUTE:
            self.show_operations()

    @Slot()
    def show_operations(self) -> None:
        """Return to the operations workspace without discarding its selection."""

        if self._active_operation_page.is_active:
            return
        if self._page_stack.currentWidget() is self._safety_verification_page:
            self._safety_verification_page.deactivate()
        self._page_stack.setCurrentWidget(self._operations_page)
        self._page_title.setText("Trabalhos")
        self._page_context.setText("Ambiente do operador")

    @Slot(object)
    def show_safety_verification(self, value: object) -> None:
        """Open a fresh pre-verification view for a validated operation."""

        if not isinstance(value, Operation):
            return
        if self._active_operation_page.is_active:
            return
        if self._page_stack.currentWidget() is self._safety_verification_page:
            self._safety_verification_page.deactivate()
        self._safety_verification_page.set_operation(value)
        self._page_stack.setCurrentWidget(self._safety_verification_page)
        self._page_title.setText("Verificação de segurança")
        self._page_context.setText("Preparação para liberação")
        self._safety_verification_page.activate()

    def show_active_operation(
        self,
        work_session: WorkSession,
        operation: Operation,
    ) -> None:
        """Transition from verified preparation to the active local session."""

        if self._page_stack.currentWidget() is self._safety_verification_page:
            self._safety_verification_page.deactivate()
        self._active_operation_page.set_work_session(work_session, operation)
        self._page_stack.setCurrentWidget(self._active_operation_page)
        self._page_title.setText("Operação ativa")
        self._page_context.setText(operation.name)
        self._active_operation_page.activate_monitoring()

    def close_active_operation(self) -> None:
        """Clear the completed session view and return to available operations."""

        self._active_operation_page.clear()
        self._page_stack.setCurrentWidget(self._operations_page)
        self._page_title.setText("Trabalhos")
        self._page_context.setText("Ambiente do operador")

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label
