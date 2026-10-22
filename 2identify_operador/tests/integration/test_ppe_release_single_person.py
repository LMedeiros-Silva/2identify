"""Release only for exactly one identified person wearing all of their required PPE."""

from __future__ import annotations

from time import monotonic

from PySide6.QtWidgets import QLabel, QPushButton

from app.domain import OperationStartAuthorization
from app.domain.camera_source import CameraSource, CameraType
from app.vision.pose import PersonPose, PoseDetectionBatch, PoseKeypoint
from app.vision.ppe import DetectionBox, PpeDetection, PpeDetectionBatch
from tests.integration.test_operation_release import _HEAD, _controller, _page, _person
from tests.integration.test_ppe_release_per_item import _BOX, MODEL_CLASSES, _operation

Box = tuple[float, float, float, float]


def _shifted(person: PersonPose, dx: float) -> PersonPose:
    return PersonPose(
        person.confidence,
        tuple(PoseKeypoint(item.x + dx, item.y, item.confidence) for item in person.keypoints),
    )


def _right(box: Box, dx: float = 300) -> Box:
    return (box[0] + dx, box[1], box[2] + dx, box[3])


ANA = _person()
BRUNO = _shifted(_person(), 300)


def _frame(controller, people: tuple[PersonPose, ...] | None, *boxes: tuple[str, Box]) -> None:
    detections = tuple(
        PpeDetection(index, name, 0.9, DetectionBox(*box))
        for index, (name, box) in enumerate(boxes)
    )
    controller._latest_pose = (
        (PoseDetectionBatch(people, 640, 480, 30.0), monotonic()) if people is not None else None
    )
    controller._handle_detections(PpeDetectionBatch(detections, 640, 480, 40.0))


def _setup(qtbot, *classes: str, page=None):
    page = page or _page(qtbot, _operation(*classes))
    controller = _controller(page)
    controller._handle_model_ready(MODEL_CLASSES)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)
    return page, controller, authorized


def _blocked(page, authorized) -> str:
    assert authorized == []
    assert not page.findChild(QPushButton, "safetyStartOperationButton").isEnabled()
    return page.findChild(QLabel, "safetyReleaseDescription").text()


def test_one_person_with_all_required_ppe_is_released(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, "capacete", "luva", "bota")
    for _ in range(7):
        _frame(
            controller,
            (ANA,),
            ("capacete", _HEAD),
            ("luva", _BOX["luva"]),
            ("bota", _BOX["bota"]),
        )
    assert len(authorized) == 1
    assert set(authorized[0].verified_ppe_ids) == {1, 2, 3}


def test_ppe_split_between_two_people_never_releases(qtbot) -> None:
    """Defect: per-frame class sets mixed Ana's gloves with Bruno's boots."""

    page, controller, authorized = _setup(qtbot, "luva", "bota")
    for _ in range(16):
        _frame(controller, (ANA, BRUNO), ("luva", _BOX["luva"]), ("bota", _right(_BOX["bota"])))
    assert "2 pessoas" in _blocked(page, authorized)


def test_two_people_both_fully_equipped_still_block_until_one_leaves(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, "luva")
    for _ in range(16):
        _frame(controller, (ANA, BRUNO), ("luva", _BOX["luva"]), ("luva", _right(_BOX["luva"])))
    assert "2 pessoas" in _blocked(page, authorized)
    # Evidence gathered while two people were present is discarded, not reused.
    for _ in range(4):
        _frame(controller, (ANA,), ("luva", _BOX["luva"]))
    assert authorized == []  # a fresh window of Ana's own frames is required
    _frame(controller, (ANA,), ("luva", _BOX["luva"]))
    assert len(authorized) == 1


def test_ppe_without_any_person_never_releases(qtbot) -> None:
    """Defect: a glove lying on the bench released the operation with nobody in view."""

    page, controller, authorized = _setup(qtbot, "luva")
    for _ in range(16):
        _frame(controller, (), ("luva", _BOX["luva"]))
    assert "nenhuma pessoa" in _blocked(page, authorized)


def test_ppe_without_a_pose_estimate_never_releases(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, "luva")
    for _ in range(16):
        _frame(controller, None, ("luva", _BOX["luva"]))
    assert "postura" in _blocked(page, authorized)


def test_ppe_of_someone_outside_the_identified_person_does_not_count(qtbot) -> None:
    """Only Ana is identified; the glove at the far edge belongs to someone pose missed."""

    page, controller, authorized = _setup(qtbot, "luva")
    for _ in range(16):
        _frame(controller, (ANA,), ("luva", _right(_BOX["luva"], 450)))
    assert "Luvas" in _blocked(page, authorized)


def test_person_without_reliable_face_and_shoulders_is_inconclusive(qtbot) -> None:
    turned = PersonPose(
        0.9,
        tuple(
            PoseKeypoint(item.x, item.y, 0.0 if index < 5 else item.confidence)
            for index, item in enumerate(_person().keypoints)
        ),
    )
    page, controller, authorized = _setup(qtbot, "luva")
    for _ in range(16):
        _frame(controller, (turned,), ("luva", _BOX["luva"]))
    assert "referência confiável" in _blocked(page, authorized)


def test_absent_or_inconclusive_ppe_of_the_single_person_blocks(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, "luva", "bota")
    for index in range(16):
        boxes = [("luva", _BOX["luva"])]
        if index % 2:
            boxes.append(("bota", _BOX["bota"]))
        _frame(controller, (ANA,), *boxes)
    assert _blocked(page, authorized).startswith("Falta confirmar: Botas: ")


def test_multicamera_release_uses_one_person_of_the_risk_area_camera(qtbot) -> None:
    page = _page(qtbot, _operation("capacete", "luva", risk_camera=2))
    page.enable_multicamera_catalog()
    page.set_cameras(
        41,
        (
            CameraSource(1, "Webcam", 3, CameraType.USB),
            CameraSource(2, "Fresa IP", 3, CameraType.IP),
        ),
    )
    for check in page._camera_checks.values():
        check.setChecked(True)
    page, controller, authorized = _setup(qtbot, page=page)
    assert page.verification_camera.camera_id == 2
    for _ in range(16):
        _frame(controller, (ANA, BRUNO), ("capacete", _HEAD), ("luva", _right(_BOX["luva"])))
    assert "2 pessoas" in _blocked(page, authorized)
    for _ in range(7):
        _frame(controller, (ANA,), ("capacete", _HEAD), ("luva", _BOX["luva"]))
    assert len(authorized) == 1
