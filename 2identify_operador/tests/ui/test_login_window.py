from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QStackedWidget, QToolButton

from app.core.config import AppSettings
from app.domain import LoginCredentials, OperatorIdentity
from app.ui.components.password_input import PasswordInput
from app.ui.login import LoginWindow
from app.ui.login.credential_login_panel import CredentialLoginPanel
from app.ui.login.face_login_panel import FaceLoginPanel, ProfileAvatar


def _create_window(qtbot) -> LoginWindow:
    window = LoginWindow(AppSettings(_env_file=None))
    qtbot.addWidget(window)
    window.show()
    return window


def _show_credentials(window: LoginWindow, qtbot) -> CredentialLoginPanel:
    face_panel = window.findChild(FaceLoginPanel, "faceLoginPanel")
    fallback_button = face_panel.findChild(QPushButton, "secondaryAuthButton")
    qtbot.mouseClick(fallback_button, Qt.MouseButton.LeftButton)
    return window.findChild(CredentialLoginPanel, "credentialLoginPanel")


def test_face_id_is_the_default_authentication_mode(qtbot) -> None:
    window = _create_window(qtbot)
    stack = window.findChild(QStackedWidget, "authenticationStack")
    face_panel = window.findChild(FaceLoginPanel, "faceLoginPanel")

    assert stack.currentWidget() is face_panel
    assert window.findChild(QLabel, "accessBadge").text() == "FACE ID · ACESSO SEGURO"


def test_disabled_face_auth_opens_credentials_without_face_switch(qtbot) -> None:
    window = LoginWindow(AppSettings(_env_file=None, face_auth_enabled=False))
    qtbot.addWidget(window)
    window.show()
    stack = window.findChild(QStackedWidget, "authenticationStack")
    credential_panel = window.findChild(CredentialLoginPanel, "credentialLoginPanel")
    face_button = credential_panel.findChild(QPushButton, "secondaryAuthButton")

    assert stack.currentWidget() is credential_panel
    assert not face_button.isVisible()


def test_face_scan_emits_request_and_enters_starting_state(qtbot) -> None:
    window = _create_window(qtbot)
    face_panel = window.findChild(FaceLoginPanel, "faceLoginPanel")
    scan_button = face_panel.findChild(QPushButton, "faceScanButton")

    with qtbot.waitSignal(window.face_login_requested, timeout=1_000):
        qtbot.mouseClick(scan_button, Qt.MouseButton.LeftButton)

    status = face_panel.findChild(QLabel, "faceStatusText")
    assert status.text() == "Inicializando câmera segura..."
    assert not scan_button.isEnabled()


def test_camera_frame_changes_status_to_scanning(qtbot) -> None:
    window = _create_window(qtbot)
    frame = QImage(320, 240, QImage.Format.Format_RGB32)
    frame.fill(Qt.GlobalColor.black)

    window.update_face_frame(frame)

    status = window.findChild(QLabel, "faceStatusText")
    assert status.text() == "Procurando um rosto cadastrado..."


def test_recognized_operator_shows_name_and_welcome_card(qtbot) -> None:
    window = _create_window(qtbot)
    identity = OperatorIdentity(operator_id=8, name="Marina Costa", confidence=0.96)

    window.show_operator_recognized(identity)

    operator_name = window.findChild(QLabel, "recognizedOperatorName")
    operator_detail = window.findChild(QLabel, "recognizedOperatorDetail")
    welcome = window.findChild(QLabel, "welcomeEyebrow")
    assert operator_name.text() == "Marina Costa"
    assert operator_detail.text() == "Operador #8 · Acesso autorizado"
    assert welcome.text() == "BEM-VINDO"
    assert operator_name.isVisible()


def test_registered_portrait_is_forwarded_to_circular_avatar(qtbot) -> None:
    window = _create_window(qtbot)
    identity = OperatorIdentity(operator_id=8, name="Marina Costa", confidence=0.96)
    portrait = QImage(80, 100, QImage.Format.Format_RGB32)
    portrait.fill(Qt.GlobalColor.darkCyan)

    window.show_operator_recognized(identity, portrait)

    avatar = window.findChild(ProfileAvatar, "operatorPhoto")
    assert avatar.has_portrait


def test_fallback_button_opens_credential_login(qtbot) -> None:
    window = _create_window(qtbot)
    credential_panel = _show_credentials(window, qtbot)
    stack = window.findChild(QStackedWidget, "authenticationStack")

    assert stack.currentWidget() is credential_panel
    assert window.findChild(QLabel, "accessBadge").text() == "ACESSO ALTERNATIVO"


def test_empty_credential_form_shows_local_validation(qtbot) -> None:
    window = _create_window(qtbot)
    credential_panel = _show_credentials(window, qtbot)
    button = credential_panel.findChild(QPushButton, "loginButton")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    username_error = credential_panel.findChild(QLabel, "usernameError")
    password_error = credential_panel.findChild(QLabel, "passwordError")
    assert username_error.text() == "Informe seu e-mail ou usuário."
    assert password_error.text() == "Informe sua senha."
    assert button.isEnabled()


def test_valid_credential_form_emits_safe_request(qtbot) -> None:
    window = _create_window(qtbot)
    credential_panel = _show_credentials(window, qtbot)
    username = credential_panel.findChild(QLineEdit, "usernameInput")
    password = credential_panel.findChild(PasswordInput, "passwordInput")
    button = credential_panel.findChild(QPushButton, "loginButton")
    username.setText("  operador@empresa.com  ")
    password.editor.setText("senha-segura")

    with qtbot.waitSignal(window.credential_login_requested, timeout=1_000) as emitted:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    request = emitted.args[0]
    assert isinstance(request, LoginCredentials)
    assert request.username == "operador@empresa.com"
    assert request.password == "senha-segura"
    assert not button.isEnabled()


def test_password_visibility_control(qtbot) -> None:
    window = _create_window(qtbot)
    credential_panel = _show_credentials(window, qtbot)
    password = credential_panel.findChild(PasswordInput, "passwordInput")
    toggle = password.findChild(QToolButton, "passwordToggleButton")

    assert password.editor.echoMode() is QLineEdit.EchoMode.Password
    qtbot.mouseClick(toggle, Qt.MouseButton.LeftButton)
    assert password.editor.echoMode() is QLineEdit.EchoMode.Normal
    assert toggle.text() == "OCULTAR"


def test_authentication_notice_restores_credential_form(qtbot) -> None:
    window = _create_window(qtbot)
    credential_panel = _show_credentials(window, qtbot)
    password = credential_panel.findChild(PasswordInput, "passwordInput")
    button = credential_panel.findChild(QPushButton, "loginButton")
    password.editor.setText("temporaria")
    window.set_credential_authenticating(True)

    window.show_credential_authentication_notice("Integração pendente.")

    status = credential_panel.findChild(QLabel, "loginStatusText")
    assert status.text() == "Integração pendente."
    assert password.text() == ""
    assert button.isEnabled()
