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
from app.domain.camera_source import CameraSource
from app.ui.active import ActiveOperationPage
from app.ui.components.sidebar import WORKS_ROUTE, Sidebar
from app.ui.operations import OperationsPage
from app.ui.safety import SafetyVerificationPage

_AUTHENTICATION_LABELS = {
    AuthenticationMethod.FACE_ID: "Face ID",
    AuthenticationMethod.CREDENTIALS: "Credenciais",
}


def _initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


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
        header.setFixedHeight(64)
        self._header = header
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 0, 24, 0)
        layout.setSpacing(14)

        page_context = QVBoxLayout()
        page_context.setSpacing(0)
        page_context.addStretch(1)
        self._page_context = self._label(
            "Ambiente do operador",
            "mainPageContext",
        )
        page_context.addWidget(self._page_context)
        self._page_title = self._label("Trabalhos", "mainPageTitle")
        page_context.addWidget(self._page_title)
        page_context.addStretch(1)
        layout.addLayout(page_context)
        layout.addStretch(1)

        session_status = self._label("SESSÃO ATIVA", "mainSessionBadge")
        session_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        session_status.setFixedHeight(26)
        layout.addWidget(session_status, 0, Qt.AlignmentFlag.AlignVCenter)

        divider = QFrame()
        divider.setObjectName("mainHeaderDivider")
        divider.setFixedSize(1, 30)
        layout.addWidget(divider, 0, Qt.AlignmentFlag.AlignVCenter)

        avatar = self._label(_initials(self._session.operator_name), "mainOperatorAvatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(36, 36)
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        operator = QVBoxLayout()
        operator.setSpacing(0)
        operator.addStretch(1)
        operator_name = self._label(self._session.operator_name, "mainOperatorName")
        operator.addWidget(operator_name)
        authentication = _AUTHENTICATION_LABELS[self._session.authentication_method]
        operator_detail = self._label(
            f"Operador #{self._session.operator_id} · {authentication}",
            "mainOperatorDetail",
        )
        operator.addWidget(operator_detail)
        operator.addStretch(1)
        layout.addLayout(operator)
        return header

    def _set_monitoring_layout(self, monitoring: bool) -> None:
        """Give the cameras the whole workspace while an operation is active."""

        self._header.setVisible(not monitoring)
        self._sidebar.set_compact(monitoring)

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
        self._set_monitoring_layout(False)

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
        self._set_monitoring_layout(False)
        self._safety_verification_page.activate()

    def show_active_operation(
        self,
        work_session: WorkSession,
        operation: Operation,
        cameras: tuple[CameraSource, ...] = (),
    ) -> None:
        """Transition from verified preparation to the active local session."""

        if self._page_stack.currentWidget() is self._safety_verification_page:
            self._safety_verification_page.deactivate()
        self._active_operation_page.set_work_session(work_session, operation)
        self._active_operation_page.set_cameras(cameras)
        self._page_stack.setCurrentWidget(self._active_operation_page)
        self._page_title.setText("Operação ativa")
        self._page_context.setText(operation.name)
        self._set_monitoring_layout(True)
        self._active_operation_page.activate_monitoring()

    def close_active_operation(self) -> None:
        """Clear the completed session view and return to available operations."""

        self._active_operation_page.clear()
        self._page_stack.setCurrentWidget(self._operations_page)
        self._page_title.setText("Trabalhos")
        self._page_context.setText("Ambiente do operador")
        self._set_monitoring_layout(False)

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label
