from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
from PySide6.QtWidgets import QLabel

from app.controllers.active_camera_controller import ActiveCameraController
from app.controllers.active_ppe_monitoring_controller import (
    ActivePpeMonitoringController,
)
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import Operation, PpeRequirement, WorkSession, WorkSessionStatus
from app.ui.active import ActiveOperationPage
from app.ui.components import CameraFrameView
from app.vision.ppe import DetectionBox, PpeDetection
from app.workers.ppe_inference_worker import PpeInferenceWorker
from app.workers.safety_camera_worker import SafetyCameraWorker

_STARTED_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


class CameraStub:
    def __init__(self) -> None:
        self.closed = False
        self.frame = np.zeros((120, 160, 3), dtype=np.uint8)

    def open(self) -> bool:
        return True

    def read(self):
        return True, self.frame.copy()

    def close(self) -> None:
        self.closed = True


class DetectorStub:
    class_names = ("capacete",)

    def detect(self, frame):
        del frame
        return (
            PpeDetection(
                0,
                "capacete",
                0.94,
                DetectionBox(10, 10, 90, 110),
            ),
        )


class MissingDetectorStub:
    class_names = ("capacete",)

    def detect(self, frame):
        del frame
        return ()


def _page() -> ActiveOperationPage:
    operator = OperatorSession(
        15,
        "João Silva",
        _STARTED_AT - timedelta(hours=1),
        AuthenticationMethod.FACE_ID,
    )
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
    )
    work_session = WorkSession(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),
        operator_id=15,
        operation_id=41,
        camera_id=None,
        risk_area_id=None,
        verified_ppe_ids=(1,),
        safety_verified_at=_STARTED_AT - timedelta(milliseconds=100),
        ppe_sample_count=2,
        ppe_window_size=2,
        started_at=_STARTED_AT,
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
    )
    page = ActiveOperationPage(operator)
    page.set_work_session(work_session, operation)
    return page


def test_active_controllers_monitor_ppe_until_work_session_stops(qtbot) -> None:
    page = _page()
    qtbot.addWidget(page)
    camera = CameraStub()
    settings = AppSettings(
        _env_file=None,
        ppe_stability_window_frames=2,
        ppe_stability_minimum_frames=2,
        ppe_stability_present_ratio=0.75,
        ppe_stability_absent_ratio=0.25,
    )
    camera_controller = ActiveCameraController(
        settings,
        page,
        worker_factory=lambda: SafetyCameraWorker(
            camera_factory=lambda: camera,
            preview_fps=30,
            maximum_failed_reads=3,
            analysis_fps=15,
        ),
    )
    inference_controller = ActivePpeMonitoringController(
        settings,
        page,
        camera_controller,
        worker_factory=lambda: PpeInferenceWorker(detector_factory=DetectorStub),
    )

    page.activate_monitoring()

    state = page.findChild(QLabel, "activePpeState")
    preview = page.findChild(CameraFrameView, "activeCameraPreview")
    qtbot.waitUntil(
        lambda: state.text() == "CONFIRMADO" and preview.has_frame,
        timeout=2_000,
    )
    assert preview.overlay_box_count == 1
    assert preview.overlay_labels == ("#1 capacete",)
    assert page.findChild(QLabel, "activeOverlayStatus").text() == (
        "1 TRACK · CONFIRMADO"
    )
    assert page.findChild(QLabel, "activeMonitoringStatus").text() == (
        "EPIs CONFORMES NO MONITORAMENTO ATUAL"
    )

    page.deactivate_monitoring()

    qtbot.waitUntil(
        lambda: camera.closed
        and not camera_controller.is_running
        and not inference_controller.is_running,
        timeout=2_000,
    )
    assert not preview.has_frame
    inference_controller.shutdown()
    camera_controller.shutdown()


def test_active_monitoring_raises_one_local_alert_for_persistent_absence(
    qtbot,
) -> None:
    page = _page()
    qtbot.addWidget(page)
    camera = CameraStub()
    settings = AppSettings(
        _env_file=None,
        ppe_stability_window_frames=2,
        ppe_stability_minimum_frames=2,
        ppe_stability_present_ratio=0.75,
        ppe_stability_absent_ratio=0.25,
        alert_minimum_consecutive_observations=2,
        alert_minimum_persistence_seconds=0,
        alert_resolution_consecutive_observations=2,
        alert_cooldown_seconds=30,
    )
    camera_controller = ActiveCameraController(
        settings,
        page,
        worker_factory=lambda: SafetyCameraWorker(
            camera_factory=lambda: camera,
            preview_fps=30,
            maximum_failed_reads=3,
            analysis_fps=15,
        ),
    )
    inference_controller = ActivePpeMonitoringController(
        settings,
        page,
        camera_controller,
        worker_factory=lambda: PpeInferenceWorker(
            detector_factory=MissingDetectorStub
        ),
    )
    emitted_updates = []
    inference_controller.local_alert_update_ready.connect(emitted_updates.append)

    page.activate_monitoring()

    qtbot.waitUntil(lambda: page.active_alert_count == 1, timeout=2_000)
    assert page.findChild(QLabel, "activePpeState").text() == "AUSENTE"
    assert page.findChild(QLabel, "activeAlertBadge").text() == (
        "1 ALERTA LOCAL ATIVO"
    )
    assert len(emitted_updates) == 1

    qtbot.wait(150)
    assert len(emitted_updates) == 1
    page.deactivate_monitoring()
    inference_controller.shutdown()
    camera_controller.shutdown()
