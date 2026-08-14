from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from app.controllers.face_login_controller import FaceLoginController
from app.core.config import AppSettings
from app.ui.login import LoginWindow
from app.ui.login.face_login_panel import FaceLoginPanel


def test_controller_fails_safely_before_camera_when_no_operator_is_enrolled(
    qtbot,
    tmp_path,
) -> None:
    settings = AppSettings(
        face_auth_allow_local_authorization=True,
        face_auth_template_store_path=tmp_path / "missing-operators.json",
    )
    window = LoginWindow(settings)
    controller = FaceLoginController(settings, window)
    qtbot.addWidget(window)
    window.show()
    face_panel = window.findChild(FaceLoginPanel, "faceLoginPanel")
    scan_button = face_panel.findChild(QPushButton, "faceScanButton")
    status = face_panel.findChild(QLabel, "faceStatusText")

    qtbot.mouseClick(scan_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: "Nenhum operador possui biometria" in status.text(),
        timeout=3_000,
    )

    assert scan_button.isEnabled()
    controller.shutdown()
