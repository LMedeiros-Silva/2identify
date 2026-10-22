"""Operation release: YOLO -> stabilization -> helmet placement -> gate -> start."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from time import monotonic

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLabel, QPushButton

from app.controllers.ppe_inference_controller import PpeInferenceController
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import OperationStartAuthorization
from app.domain.camera_source import CameraSource, CameraType
from app.domain.operation import Operation, PpeRequirement, RiskAreaReference
from app.ui.safety import SafetyCameraState, SafetyVerificationPage
from app.vision.pose import (
    COCO_KEYPOINT_COUNT,
    CocoKeypoint,
    PersonPose,
    PoseDetectionBatch,
    PoseKeypoint,
)
from app.vision.ppe import DetectionBox, PpeDetection, PpeDetectionBatch
from app.workers.pose_inference_worker import PoseInferenceWorker
from app.workers.ppe_inference_worker import PpeInferenceWorker

_HEAD = (85, 25, 115, 60)
_HAND = (60, 165, 85, 190)
_GLOVE = (70, 170, 90, 190)
# Field pattern: YOLO misses the worn helmet in one frame out of five (80% presence).
_FLAKY = (True, True, True, True, False) * 4


class CameraControllerStub(QObject):
    analysis_frame_ready = Signal(object)


def _person() -> PersonPose:
    points = [PoseKeypoint(0, 0, 0) for _ in range(COCO_KEYPOINT_COUNT)]
    for key, (x, y) in {
        CocoKeypoint.NOSE: (100, 60),
        CocoKeypoint.LEFT_EYE: (94, 55),
        CocoKeypoint.RIGHT_EYE: (106, 55),
        CocoKeypoint.LEFT_EAR: (88, 60),
        CocoKeypoint.RIGHT_EAR: (112, 60),
        CocoKeypoint.LEFT_SHOULDER: (80, 100),
        CocoKeypoint.RIGHT_SHOULDER: (120, 100),
        CocoKeypoint.LEFT_WRIST: (75, 180),
        CocoKeypoint.RIGHT_WRIST: (125, 180),
    }.items():
        points[int(key)] = PoseKeypoint(x, y, 0.95)
    return PersonPose(0.95, tuple(points))


def _operation(*, gloves: bool = False, risk_camera: int | None = None) -> Operation:
    required = [PpeRequirement(1, "Capacete", "capacete")]
    if gloves:
        required.append(PpeRequirement(2, "Luvas", "luva"))
    risk_area = (
        RiskAreaReference(7, "Fresa", camera_id=risk_camera) if risk_camera is not None else None
    )
    return Operation(41, "Fresagem", required_ppe=tuple(required), risk_area=risk_area)


def _page(qtbot, operation: Operation) -> SafetyVerificationPage:
    page = SafetyVerificationPage(
        OperatorSession(15, "Operador", datetime.now(UTC), AuthenticationMethod.FACE_ID)
    )
    qtbot.addWidget(page)
    page.set_operation(operation)
    return page


def _controller(page: SafetyVerificationPage, **settings) -> PpeInferenceController:
    controller = PpeInferenceController(
        settings=AppSettings(_env_file=None, **settings),
        page=page,
        camera_controller=CameraControllerStub(),
        worker_factory=lambda: pytest.fail("the model is driven by the test"),
        pose_worker_factory=lambda: pytest.fail("the pose is driven by the test"),
    )
    # The camera route is open and the model loaded, as after page.activate().
    page._camera_active = True
    page.set_camera_state(SafetyCameraState.ACTIVE, "Câmera conectada.")
    controller._handle_model_ready(("bota", "capacete", "luva"))
    return controller


def _frame(
    controller: PpeInferenceController,
    *boxes: tuple[str, tuple[float, float, float, float]],
    pose: bool = True,
) -> None:
    detections = tuple(
        PpeDetection(index, name, 0.9, DetectionBox(*box))
        for index, (name, box) in enumerate(boxes)
    )
    controller._latest_pose = (
        (PoseDetectionBatch((_person(),), 640, 480, 30.0), monotonic()) if pose else None
    )
    controller._handle_detections(PpeDetectionBatch(detections, 640, 480, 40.0))


def _run(controller, pattern, *extra, pose: bool = True) -> None:
    for helmet in pattern:
        boxes = (("capacete", _HEAD),) if helmet else ()
        _frame(controller, *boxes, *extra, pose=pose)


def _texts(page: SafetyVerificationPage) -> tuple[str, str]:
    return (
        page.findChild(QLabel, "safetyReleaseStatus").text(),
        page.findChild(QLabel, "safetyPpeState").text(),
    )


def test_complete_ppe_starts_the_operation_without_a_click(qtbot) -> None:
    page = _page(qtbot, _operation())
    controller = _controller(page)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    _run(controller, (True,) * 4)
    assert authorized == []
    assert _texts(page)[1] == "VERIFICANDO"
    _run(controller, (True,))

    assert len(authorized) == 1
    assert authorized[0].operation_id == 41
    assert authorized[0].verified_ppe_ids == (1,)
    assert _texts(page)[0] == "INÍCIO AUTORIZADO"
    # One-shot: later frames cannot authorize the same visit twice.
    _run(controller, (True,) * 8)
    assert len(authorized) == 1


def test_a_missed_frame_does_not_erase_the_helmet_on_head_evidence(qtbot) -> None:
    """Field report: boxes on screen, yet the operation was never released."""

    page = _page(qtbot, _operation())
    controller = _controller(page)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    _run(controller, _FLAKY)

    assert len(authorized) == 1


@pytest.mark.parametrize(
    ("pattern", "pose", "ppe_text"),
    [
        ((False,) * 20, True, "VERIFICANDO"),  # no helmet seen: unknown, not absent
        ((True, False) * 10, True, "VERIFICANDO"),  # 50%: inconclusive
        ((True,) * 20, False, "VERIFICANDO"),  # no pose: placement unknown
    ],
)
def test_missing_or_inconclusive_helmet_never_starts(qtbot, pattern, pose, ppe_text) -> None:
    page = _page(qtbot, _operation())
    controller = _controller(page)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    _run(controller, pattern, pose=pose)

    assert authorized == []
    assert _texts(page) == ("AGUARDANDO ESTABILIDADE", ppe_text)
    assert not page.findChild(QPushButton, "safetyStartOperationButton").isEnabled()


def test_helmet_in_the_hand_blocks_the_start(qtbot) -> None:
    page = _page(qtbot, _operation())
    controller = _controller(page)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    for _ in range(10):
        _frame(controller, ("capacete", _HAND))

    assert authorized == []
    assert _texts(page) == ("EPI AUSENTE", "NA MÃO")


def test_every_required_ppe_must_be_confirmed(qtbot) -> None:
    page = _page(qtbot, _operation(gloves=True))
    controller = _controller(page)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    # Helmet on the head, gloves seen in half of the frames: inconclusive, no start.
    for index in range(16):
        gloves = (("luva", _GLOVE),) if index % 2 else ()
        _frame(controller, ("capacete", _HEAD), *gloves)
    assert authorized == []
    labels = [label.text() for label in page.findChildren(QLabel, "safetyPpeState")]
    assert labels == ["NA CABEÇA", "INCONCLUSIVO"]

    for _ in range(8):
        _frame(controller, ("capacete", _HEAD), ("luva", _GLOVE))
    assert len(authorized) == 1
    assert set(authorized[0].verified_ppe_ids) == {1, 2}


def test_requirement_without_model_class_is_blocked(qtbot) -> None:
    page = _page(qtbot, _operation(gloves=True))
    controller = _controller(page)
    controller._handle_model_ready(("capacete",))
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    _run(controller, (True,) * 10)

    assert authorized == []
    assert _texts(page)[0] == "SEM MAPEAMENTO"


def test_pose_unavailable_is_explained_instead_of_waiting_silently(qtbot) -> None:
    page = _page(qtbot, _operation())
    controller = _controller(page)

    controller._handle_pose_failure("modelo de postura ausente", True)
    _run(controller, (True,) * 10, pose=False)

    description = page.findChild(QLabel, "safetyReleaseDescription").text()
    # Without pose nobody can be identified, so no PPE (helmet included) is confirmed.
    assert description == (
        "Falta confirmar: Pessoa: estimativa de postura indisponível, "
        "não é possível confirmar uma única pessoa."
    )
    assert not page.findChild(QPushButton, "safetyStartOperationButton").isEnabled()


def test_rejected_session_rearms_the_gate_without_an_automatic_loop(qtbot) -> None:
    """A failed WorkSession start used to leave the gate ignoring every detection."""

    page = _page(qtbot, _operation())
    controller = _controller(page)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)
    _run(controller, (True,) * 5)
    assert len(authorized) == 1

    controller.handle_operation_start_rejected()
    page.show_operation_start_rejected()
    _run(controller, (True,) * 8)

    # Fresh evidence is collected again and the button is the way to retry.
    assert len(authorized) == 1
    button = page.findChild(QPushButton, "safetyStartOperationButton")
    assert button.isEnabled()
    button.click()
    assert len(authorized) == 2


def test_manual_mode_keeps_the_button_and_its_gate(qtbot) -> None:
    page = _page(qtbot, _operation())
    controller = _controller(page, ppe_auto_start_enabled=False)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    _run(controller, (True,) * 6)
    assert authorized == []
    page.findChild(QPushButton, "safetyStartOperationButton").click()
    assert len(authorized) == 1


def test_multicamera_verification_uses_the_risk_area_camera_and_keeps_selection(qtbot) -> None:
    page = _page(qtbot, _operation(risk_camera=2))
    page.enable_multicamera_catalog()
    cameras = (
        CameraSource(1, "Webcam", 3, CameraType.USB),
        CameraSource(2, "Fresa IP", 3, CameraType.IP),
    )
    page.set_cameras(41, cameras)
    page._camera_checks[1].setChecked(True)
    page._refresh_camera_selection()
    controller = _controller(page)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)

    _run(controller, _FLAKY)

    assert page.verification_camera.camera_id == 2
    assert [camera.camera_id for camera in page.selected_cameras] == [1, 2]
    assert len(authorized) == 1


class _BlockingDetector:
    release = threading.Event()
    class_names = ("capacete",)

    def __init__(self) -> None:
        self.release.wait(5)

    def detect(self, frame):
        return ()


class _Detector:
    class_names = ("capacete",)

    def detect(self, frame):
        return ()


def test_start_while_previous_verification_stops_is_deferred_not_dropped(qtbot) -> None:
    page = _page(qtbot, _operation())
    factories = iter((_BlockingDetector, _Detector))
    controller = PpeInferenceController(
        settings=AppSettings(_env_file=None, pose_estimation_enabled=False),
        page=page,
        camera_controller=CameraControllerStub(),
        worker_factory=lambda: PpeInferenceWorker(detector_factory=next(factories)),
        pose_worker_factory=lambda: PoseInferenceWorker(estimator_factory=lambda: None),
    )
    page._camera_active = True
    _BlockingDetector.release.clear()
    controller.start()
    first = controller._worker
    controller.stop()
    controller.start()  # the operator reopened the verification immediately
    assert controller._worker is first

    _BlockingDetector.release.set()
    qtbot.waitUntil(lambda: controller._model_ready, timeout=3_000)
    assert controller._worker is not first
    assert controller.shutdown()
