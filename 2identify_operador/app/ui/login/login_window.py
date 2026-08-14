"""Authentication shell with biometric-first and credential fallback flows."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppSettings
from app.domain.auth import OperatorIdentity
from app.ui.login.brand_panel import IndustrialBrandPanel
from app.ui.login.credential_login_panel import CredentialLoginPanel
from app.ui.login.face_login_panel import FaceLoginPanel, FaceLoginState


class LoginWindow(QMainWindow):
    """Authentication view that delegates all camera, AI and network work."""

    face_login_requested = Signal()
    face_login_cancel_requested = Signal()
    credential_login_requested = Signal(object)

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings
        self._was_centered = False

        self.setObjectName("loginWindow")
        self.setWindowTitle("2Identify Operator · Acesso")
        self.setMinimumSize(1060, 690)
        self.resize(1240, 760)
        self.setCentralWidget(self._build_content())
        if not self._settings.face_auth_enabled:
            self._credential_panel.set_face_login_available(False)
            self.show_credential_login()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._was_centered:
            available_area = self.screen().availableGeometry()
            self.move(available_area.center() - self.rect().center())
            self._was_centered = True
        self._active_panel().focus_initial_control()

    def update_face_frame(self, frame: QImage) -> None:
        """Receive a Qt frame from the future camera controller."""

        self._face_panel.update_frame(frame)

    def set_face_authentication_state(self, state: FaceLoginState, message: str) -> None:
        self._face_panel.set_state(state, message)

    def show_operator_recognized(
        self,
        identity: OperatorIdentity,
        portrait: QImage | None = None,
    ) -> None:
        """Present the registered photo and welcome message after a valid match."""

        self.show_face_login()
        self._face_panel.show_identity(identity, portrait)

    def show_face_authentication_error(self, message: str, unavailable: bool = False) -> None:
        self._face_panel.show_error(message, unavailable=unavailable)

    def set_credential_authenticating(self, is_authenticating: bool) -> None:
        self._credential_panel.set_authenticating(is_authenticating)

    def show_credential_authentication_error(self, message: str) -> None:
        self._credential_panel.show_error(message)

    def show_credential_authentication_notice(self, message: str) -> None:
        self._credential_panel.show_notice(message)

    @Slot()
    def show_face_login(self) -> None:
        if not self._settings.face_auth_enabled:
            self.show_credential_login()
            return
        self._stack.setCurrentWidget(self._face_panel)
        self._access_badge.setText("FACE ID · ACESSO SEGURO")
        self._face_panel.set_state(
            FaceLoginState.READY,
            "Pronto para iniciar o reconhecimento facial.",
        )
        self._face_panel.focus_initial_control()

    @Slot()
    def show_credential_login(self) -> None:
        self.face_login_cancel_requested.emit()
        self._stack.setCurrentWidget(self._credential_panel)
        self._access_badge.setText("ACESSO ALTERNATIVO")
        self._credential_panel.focus_initial_control()

    def _build_content(self) -> QWidget:
        root = QWidget()
        root.setObjectName("loginRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(IndustrialBrandPanel(), 10)
        layout.addWidget(self._build_authentication_panel(), 10)
        return root

    def _build_authentication_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("loginFormPanel")
        outer_layout = QVBoxLayout(panel)
        outer_layout.setContentsMargins(44, 34, 44, 28)
        outer_layout.setSpacing(0)

        top_line = QHBoxLayout()
        top_line.addStretch()
        self._access_badge = self._label("FACE ID · ACESSO SEGURO", "accessBadge")
        top_line.addWidget(self._access_badge)
        outer_layout.addLayout(top_line)
        outer_layout.addStretch(1)

        self._face_panel = FaceLoginPanel()
        self._credential_panel = CredentialLoginPanel()
        self._face_panel.scan_requested.connect(self.face_login_requested)
        self._face_panel.credentials_requested.connect(self.show_credential_login)
        self._credential_panel.face_login_requested.connect(self.show_face_login)
        self._credential_panel.login_requested.connect(self.credential_login_requested)

        self._stack = QStackedWidget()
        self._stack.setObjectName("authenticationStack")
        self._stack.setMinimumWidth(420)
        self._stack.setMaximumWidth(460)
        self._stack.addWidget(self._face_panel)
        self._stack.addWidget(self._credential_panel)
        self._stack.setCurrentWidget(self._face_panel)
        outer_layout.addWidget(self._stack, 0, Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addStretch(1)

        footer = self._label(
            f"2Identify Operator · Versão {self._settings.app_version}",
            "loginFooter",
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_layout.addWidget(footer)
        return panel

    def _active_panel(self) -> FaceLoginPanel | CredentialLoginPanel:
        if self._stack.currentWidget() is self._credential_panel:
            return self._credential_panel
        return self._face_panel

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label
