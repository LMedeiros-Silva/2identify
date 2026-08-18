from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton

from app.controllers.credential_login_controller import CredentialLoginController
from app.core.config import AppSettings
from app.domain import CredentialAuthenticationResult, LoginCredentials
from app.services.auth_service import AuthService
from app.ui.components.password_input import PasswordInput
from app.ui.login import LoginWindow
from app.ui.login.credential_login_panel import CredentialLoginPanel


class SuccessfulProvider:
    def authenticate_credentials(
        self,
        credentials: LoginCredentials,
    ) -> CredentialAuthenticationResult:
        assert credentials.password == "segredo"
        return CredentialAuthenticationResult(15, "João Silva", "token")


def test_controller_authenticates_without_blocking_and_updates_success_state(qtbot) -> None:
    window = LoginWindow(AppSettings(_env_file=None, face_auth_enabled=False))
    controller = CredentialLoginController(AuthService(SuccessfulProvider()), window)
    qtbot.addWidget(window)
    window.show()
    panel = window.findChild(CredentialLoginPanel, "credentialLoginPanel")
    username = panel.findChild(QLineEdit, "usernameInput")
    password = panel.findChild(PasswordInput, "passwordInput")
    button = panel.findChild(QPushButton, "loginButton")
    status = panel.findChild(QLabel, "loginStatusText")
    username.setText("operador.15")
    password.editor.setText("segredo")

    with qtbot.waitSignal(controller.operator_authenticated, timeout=2_000) as emitted:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert isinstance(emitted.args[0], CredentialAuthenticationResult)
    assert status.text() == "Acesso autorizado. Bem-vindo, João Silva."
    assert button.text() == "ACESSO AUTORIZADO"
    assert not button.isEnabled()
    assert password.text() == ""
    controller.shutdown()
