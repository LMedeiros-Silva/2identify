from datetime import UTC, datetime

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from app.controllers.ppe_inference_controller import PpeInferenceController
from app.controllers.safety_camera_controller import SafetyCameraController
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import OperationStartAuthorization
from app.domain.operation import Operation, PpeRequirement
from app.ui.components import CameraFrameView
from app.ui.safety import PpeInferenceState, SafetyCameraState, SafetyVerificationPage
from app.vision.ppe import DetectionBox, PpeDetection
from app.workers.ppe_inference_worker import PpeInferenceWorker
from app.workers.safety_camera_worker import SafetyCameraWorker


class CameraStub:
    def __init__(self, opens: bool = True) -> None:
        self.opens = opens
        self.closed = False
        self.frame = np.zeros((120, 160, 3), dtype=np.uint8)

    def open(self) -> bool:
        return self.opens

    def read(self):
        return True, self.frame.copy()

    def close(self) -> None:
        self.closed = True


def _page() -> SafetyVerificationPage:
    session = OperatorSession(
        operator_id=15,
        operator_name="João Silva",
        login_time=datetime(2026, 8, 16, 13, 30, tzinfo=UTC),
        authentication_method=AuthenticationMethod.FACE_ID,
    )
    page = SafetyVerificationPage(session)
    page.set_operation(
        Operation(
            41,
            "Inspeção de segurança",
            required_ppe=(
                PpeRequirement(1, "Capacete de segurança", "capacete"),
            ),
        )
    )
    return page


def _controller(
    page: SafetyVerificationPage,
    camera: CameraStub,
    analysis_fps: float | None = None,
) -> SafetyCameraController:
    return SafetyCameraController(
        settings=AppSettings(_env_file=None),
        page=page,
        worker_factory=lambda: SafetyCameraWorker(
            camera_factory=lambda: camera,
            preview_fps=30,
            maximum_failed_reads=3,
            analysis_fps=analysis_fps,
        ),
    )


def test_safety_camera_controller_follows_page_lifecycle(qtbot) -> None:
    page = _page()
    qtbot.addWidget(page)
    camera = CameraStub()
    controller = _controller(page, camera)

    page.activate()

    preview = page.findChild(CameraFrameView, "safetyCameraPreview")
    qtbot.waitUntil(
        lambda: page.camera_state is SafetyCameraState.ACTIVE and preview.has_frame,
        timeout=2_000,
    )
    assert page.findChild(QLabel, "safetyCameraStatus").text() == "ATIVA"
    assert page.findChild(QLabel, "safetyPpeState").text() == "AGUARDANDO"
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "OPERAÇÃO NÃO LIBERADA"
    )

    page.deactivate()

    qtbot.waitUntil(lambda: camera.closed and not controller.is_running, timeout=2_000)
    assert page.camera_state is SafetyCameraState.NOT_INITIALIZED
    assert not preview.has_frame


def test_safety_camera_controller_exposes_recoverable_unavailable_state(qtbot) -> None:
    page = _page()
    qtbot.addWidget(page)
    page.show()
    camera = CameraStub(opens=False)
    controller = _controller(page, camera)

    page.activate()

    qtbot.waitUntil(
        lambda: page.camera_state is SafetyCameraState.UNAVAILABLE,
        timeout=2_000,
    )
    retry = page.findChild(QPushButton, "safetyCameraRetryButton")
    assert retry.isVisibleTo(page)
    assert "Não foi possível abrir" in page.findChild(
        QLabel,
        "safetyCameraPlaceholderDescription",
    ).text()
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "OPERAÇÃO NÃO LIBERADA"
    )
    controller.shutdown()


class DetectorStub:
    class_names = ("bota", "capacete")

    def detect(self, frame):
        del frame
        return (
            PpeDetection(
                1,
                "capacete",
                0.91,
                DetectionBox(10, 20, 80, 100),
            ),
        )


def test_ppe_controller_rejects_start_without_current_compliant_evidence(qtbot) -> None:
    page = _page()
    qtbot.addWidget(page)
    camera_controller = _controller(page, CameraStub())
    inference_controller = PpeInferenceController(
        settings=AppSettings(_env_file=None),
        page=page,
        camera_controller=camera_controller,
        worker_factory=lambda: PpeInferenceWorker(detector_factory=DetectorStub),
    )
    authorized_operations = []
    inference_controller.operation_start_authorized.connect(
        authorized_operations.append
    )

    page.operation_start_requested.emit(41)

    assert authorized_operations == []
    assert page.findChild(QLabel, "safetyReleaseStatus").text() == (
        "VERIFICAÇÃO EXPIRADA"
    )
    assert not page.findChild(
        QPushButton,
        "safetyStartOperationButton",
    ).isEnabled()


def test_camera_and_ppe_controllers_authorize_only_stable_confirmation(qtbot) -> None:
    page = _page()
    qtbot.addWidget(page)
    camera = CameraStub()
    camera_controller = _controller(page, camera, analysis_fps=15)
    inference_controller = PpeInferenceController(
        settings=AppSettings(_env_file=None),
        page=page,
        camera_controller=camera_controller,
        worker_factory=lambda: PpeInferenceWorker(detector_factory=DetectorStub),
    )

    page.activate()

    ppe_state = page.findChild(QLabel, "safetyPpeState")
    qtbot.waitUntil(
        lambda: page.inference_state is PpeInferenceState.ACTIVE
        and ppe_state.text() == "CONFIRMADO",
        timeout=2_000,
    )
    preview = page.findChild(CameraFrameView, "safetyCameraPreview")
    assert preview.overlay_box_count == 1
    assert "1 CAIXA" in page.findChild(
        QLabel,
        "safetyDetectionOverlayStatus",
    ).text()
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "VERIFICAÇÃO CONCLUÍDA"
    )
    start_button = page.findChild(QPushButton, "safetyStartOperationButton")
    assert start_button.isEnabled()
    with qtbot.waitSignal(
        inference_controller.operation_start_authorized,
        timeout=1_000,
    ) as authorized:
        qtbot.mouseClick(start_button, Qt.MouseButton.LeftButton)
    authorization = authorized.args[0]
    assert isinstance(authorization, OperationStartAuthorization)
    assert authorization.operation_id == page.operation.operation_id
    assert authorization.verified_ppe_ids == (1,)
    assert not start_button.isEnabled()
    assert page.findChild(QLabel, "safetyReleaseStatus").text() == (
        "INÍCIO AUTORIZADO"
    )

    page.deactivate()
    assert not start_button.isEnabled()
    inference_controller.shutdown()
    camera_controller.shutdown()
    assert not inference_controller.is_running
    assert not camera_controller.is_running


def test_compliant_release_gate_expires_when_analysis_stops(qtbot) -> None:
    page = _page()
    qtbot.addWidget(page)
    camera = CameraStub()
    camera_controller = _controller(page, camera, analysis_fps=15)
    inference_controller = PpeInferenceController(
        settings=AppSettings(
            _env_file=None,
            ppe_release_assessment_max_age_seconds=0.15,
        ),
        page=page,
        camera_controller=camera_controller,
        worker_factory=lambda: PpeInferenceWorker(detector_factory=DetectorStub),
    )

    page.activate()

    start_button = page.findChild(QPushButton, "safetyStartOperationButton")
    qtbot.waitUntil(start_button.isEnabled, timeout=2_000)
    camera_controller.stop()
    qtbot.waitUntil(lambda: not camera_controller.is_running, timeout=2_000)
    qtbot.waitUntil(lambda: not start_button.isEnabled(), timeout=2_000)

    assert page.findChild(QLabel, "safetyReleaseStatus").text() == (
        "VERIFICAÇÃO EXPIRADA"
    )
    page.deactivate()
    inference_controller.shutdown()
    camera_controller.shutdown()
