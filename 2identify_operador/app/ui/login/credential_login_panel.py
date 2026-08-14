"""Secondary credential-based authentication panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain.auth import LoginCredentials
from app.ui.components.password_input import PasswordInput


class CredentialLoginPanel(QWidget):
    """Fallback login form that delegates authentication through signals."""

    login_requested = Signal(object)
    face_login_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._is_authenticating = False
        self.setObjectName("credentialLoginPanel")
        self.setMinimumWidth(420)
        self.setMaximumWidth(430)
        self._build_content()
        self._configure_keyboard_navigation()

    def focus_initial_control(self) -> None:
        self._username_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_face_login_available(self, is_available: bool) -> None:
        self._face_login_button.setVisible(is_available)

    def set_authenticating(self, is_authenticating: bool) -> None:
        self._is_authenticating = is_authenticating
        self._username_input.setEnabled(not is_authenticating)
        self._password_input.setEnabled(not is_authenticating)
        self._login_button.setEnabled(not is_authenticating)
        self._face_login_button.setEnabled(not is_authenticating)
        self._login_button.setText(
            "AUTENTICANDO..." if is_authenticating else "ENTRAR NO SISTEMA"
        )
        self._progress_bar.setVisible(is_authenticating)

    def show_error(self, message: str) -> None:
        self.set_authenticating(False)
        self._show_status(message, "error")
        self._password_input.clear()
        self._password_input.focus_editor()

    def show_notice(self, message: str) -> None:
        self.set_authenticating(False)
        self._show_status(message, "information")
        self._password_input.clear()
        self._password_input.focus_editor()

    def _build_content(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._label("ACESSO ALTERNATIVO", "formEyebrow"))
        layout.addSpacing(9)
        layout.addWidget(self._label("Entrar com credenciais", "formTitle"))
        layout.addSpacing(8)

        description = self._label(
            "Use e-mail e senha quando o reconhecimento facial não estiver disponível.",
            "formDescription",
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(22)

        layout.addWidget(self._label("E-MAIL OU USUÁRIO", "fieldLabel"))
        layout.addSpacing(7)
        self._username_input = QLineEdit()
        self._username_input.setObjectName("usernameInput")
        self._username_input.setPlaceholderText("Digite seu e-mail ou usuário")
        self._username_input.setClearButtonEnabled(True)
        self._username_input.setMaxLength(254)
        self._username_input.setAccessibleName("E-mail ou usuário")
        self._username_input.setProperty("validationState", "normal")
        self._username_input.textChanged.connect(self._clear_username_error)
        self._username_input.returnPressed.connect(self._focus_password)
        layout.addWidget(self._username_input)

        self._username_error = self._helper_label("usernameError")
        layout.addWidget(self._username_error)
        layout.addSpacing(7)

        layout.addWidget(self._label("SENHA", "fieldLabel"))
        layout.addSpacing(7)
        self._password_input = PasswordInput()
        self._password_input.text_changed.connect(self._clear_password_error)
        self._password_input.return_pressed.connect(self._submit)
        layout.addWidget(self._password_input)

        self._password_error = self._helper_label("passwordError")
        layout.addWidget(self._password_error)
        layout.addSpacing(2)

        support = self._label(
            "Problemas de acesso? Contate o administrador do sistema.",
            "supportText",
        )
        support.setWordWrap(True)
        layout.addWidget(support)
        layout.addSpacing(14)

        self._status_banner = QFrame()
        self._status_banner.setObjectName("loginStatusBanner")
        self._status_banner.setProperty("statusKind", "information")
        status_layout = QVBoxLayout(self._status_banner)
        status_layout.setContentsMargins(14, 10, 14, 10)
        self._status_label = self._label("", "loginStatusText")
        self._status_label.setWordWrap(True)
        status_layout.addWidget(self._status_label)
        self._status_banner.hide()
        layout.addWidget(self._status_banner)
        layout.addSpacing(10)

        self._login_button = QPushButton("ENTRAR NO SISTEMA")
        self._login_button.setObjectName("loginButton")
        self._login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_button.clicked.connect(self._submit)
        layout.addWidget(self._login_button)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("loginProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)
        layout.addSpacing(11)

        self._face_login_button = QPushButton("VOLTAR AO RECONHECIMENTO FACIAL")
        self._face_login_button.setObjectName("secondaryAuthButton")
        self._face_login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._face_login_button.clicked.connect(self.face_login_requested)
        layout.addWidget(self._face_login_button)

    def _configure_keyboard_navigation(self) -> None:
        QWidget.setTabOrder(self._username_input, self._password_input.editor)
        QWidget.setTabOrder(self._password_input.editor, self._login_button)
        QWidget.setTabOrder(self._login_button, self._face_login_button)

    @Slot()
    def _focus_password(self) -> None:
        self._password_input.focus_editor()

    @Slot()
    def _submit(self) -> None:
        if self._is_authenticating:
            return

        self._hide_status()
        username = self._username_input.text().strip()
        password = self._password_input.text()
        self._set_username_error("" if username else "Informe seu e-mail ou usuário.")
        self._set_password_error("" if password else "Informe sua senha.")

        if not username:
            self._username_input.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not password:
            self._password_input.focus_editor()
            return

        self.set_authenticating(True)
        self.login_requested.emit(LoginCredentials(username=username, password=password))

    @Slot(str)
    def _clear_username_error(self, _text: str) -> None:
        if self._username_error.text().strip():
            self._set_username_error("")

    @Slot(str)
    def _clear_password_error(self, _text: str) -> None:
        if self._password_error.text().strip():
            self._set_password_error("")

    def _set_username_error(self, message: str) -> None:
        self._username_error.setText(message or " ")
        self._apply_validation_state(self._username_input, bool(message))

    def _set_password_error(self, message: str) -> None:
        self._password_error.setText(message or " ")
        self._password_input.set_error(bool(message))

    def _show_status(self, message: str, kind: str) -> None:
        self._status_label.setText(message)
        self._status_banner.setProperty("statusKind", kind)
        self._refresh_style(self._status_banner)
        self._status_banner.show()

    def _hide_status(self) -> None:
        self._status_banner.hide()
        self._status_label.clear()

    @staticmethod
    def _apply_validation_state(widget: QWidget, has_error: bool) -> None:
        widget.setProperty("validationState", "error" if has_error else "normal")
        CredentialLoginPanel._refresh_style(widget)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    @staticmethod
    def _helper_label(object_name: str) -> QLabel:
        label = CredentialLoginPanel._label(" ", object_name)
        label.setFixedHeight(18)
        return label

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label
