from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from app.controllers.face_login_controller import FaceLoginController
from app.core.config import AppSettings
from app.ui.login import LoginWindow
from app.ui.login.face_login_panel import FaceLoginPanel


def test_controller_fails_safely_before_camera_when_the_station_is_not_configured(
    qtbot,
) -> None:
    settings = AppSettings(_env_file=None)
    window = LoginWindow(settings)
    controller = FaceLoginController(settings, window, api_client=object())
    qtbot.addWidget(window)
    window.show()
    face_panel = window.findChild(FaceLoginPanel, "faceLoginPanel")
    scan_button = face_panel.findChild(QPushButton, "faceScanButton")
    status = face_panel.findChild(QLabel, "faceStatusText")

    qtbot.mouseClick(scan_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: "OPERATOR_STATION_TOKEN" in status.text(),
        timeout=3_000,
    )

    assert scan_button.isEnabled()
    controller.shutdown()
