"""Every supported PPE through the release gate, alone and combined."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from app.api.client import _OperationPpePayload, _ppe_detection_class
from app.domain import OperationStartAuthorization
from app.domain.camera_source import CameraSource, CameraType
from app.domain.operation import Operation, PpeRequirement, RiskAreaReference
from tests.integration.test_operation_release import _HAND, _HEAD, _controller, _frame, _page

# Classes of the deployed best.pt (docs/metaindustria-multicamera-field-guide.md, step 10).
MODEL_CLASSES = (
    "bota",
    "capacete",
    "colete_refletivo",
    "luva",
    "mangote",
    "mao_sem_luva",
    "mascara",
    "oculos",
    "protetor_headset",
    "protetor_intra",
    "tronco_sem_colete",
)
# (ppe_id, name as registered, code, model class)
SUPPORTED = (
    (1, "Capacete", "EPI-001", "capacete"),
    (2, "Luvas", "EPI-002", "luva"),
    (3, "Botas", "EPI-003", "bota"),
    (4, "Mangote", "EPI-004", "mangote"),
    (5, "Óculos de proteção", "EPI-005", "oculos"),
    (6, "Protetor auricular", "EPI-006", "protetor_headset"),
    (7, "Colete refletivo", None, "colete_refletivo"),
    (8, "Máscara", None, "mascara"),
)
_BOX = {
    "luva": (60, 165, 90, 195),
    "bota": (80, 400, 120, 470),
    "mangote": (70, 120, 95, 170),
    "oculos": (92, 50, 108, 60),
    "protetor_headset": (84, 50, 116, 70),
    "colete_refletivo": (75, 100, 125, 220),
    "mascara": (93, 60, 107, 75),
}
_IDS = [item[3] for item in SUPPORTED]


def _operation(*classes: str, risk_camera: int | None = None) -> Operation:
    required = tuple(
        PpeRequirement(ppe_id, name, detection_class)
        for ppe_id, name, _code, detection_class in SUPPORTED
        if detection_class in classes
    )
    risk_area = (
        RiskAreaReference(7, "Fresa", camera_id=risk_camera) if risk_camera is not None else None
    )
    return Operation(41, "Fresagem", required_ppe=required, risk_area=risk_area)


def _setup(qtbot, *classes: str, **kwargs):
    page = _page(qtbot, _operation(*classes, **kwargs))
    controller = _controller(page)
    controller._handle_model_ready(MODEL_CLASSES)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)
    return page, controller, authorized


def _boxes(seen: set[str]) -> tuple[tuple[str, tuple[float, float, float, float]], ...]:
    return tuple(
        (name, _HEAD if name == "capacete" else _BOX[name]) for name in sorted(seen)
    )


def _states(page) -> list[str]:
    return [label.text() for label in page.findChildren(QLabel, "safetyPpeState")]


def _status(page) -> str:
    return page.findChild(QLabel, "safetyReleaseStatus").text()


def _description(page) -> str:
    return page.findChild(QLabel, "safetyReleaseDescription").text()


@pytest.mark.parametrize(("ppe_id", "name", "code", "detection_class"), SUPPORTED)
def test_registered_ppe_maps_to_a_class_of_the_model(ppe_id, name, code, detection_class):
    payload = _OperationPpePayload(id=ppe_id, name=name, code=code)
    assert _ppe_detection_class(payload) == detection_class
    assert detection_class in MODEL_CLASSES


@pytest.mark.parametrize("detection_class", _IDS)
def test_each_ppe_alone_is_released_when_present(qtbot, detection_class) -> None:
    page, controller, authorized = _setup(qtbot, detection_class)
    for _ in range(7):
        _frame(controller, *_boxes({detection_class}))
    assert len(authorized) == 1
    assert authorized[0].verified_ppe_ids == (_IDS.index(detection_class) + 1,)
    assert _status(page) == "INÍCIO AUTORIZADO"


@pytest.mark.parametrize("detection_class", _IDS)
def test_each_ppe_alone_survives_one_missed_frame_in_five(qtbot, detection_class) -> None:
    """Regression: field detectors miss frames; 80% presence must still confirm."""

    page, controller, authorized = _setup(qtbot, detection_class)
    for index in range(20):
        _frame(controller, *(_boxes({detection_class}) if index % 5 != 4 else ()))
    assert len(authorized) == 1


@pytest.mark.parametrize("detection_class", _IDS)
def test_each_ppe_alone_never_seen_is_unknown_not_absent(qtbot, detection_class) -> None:
    page, controller, authorized = _setup(qtbot, detection_class)
    for _ in range(16):
        _frame(controller)
    assert authorized == []
    assert _status(page) == "AGUARDANDO ESTABILIDADE"
    assert _states(page) == ["VERIFICANDO" if detection_class == "capacete" else "INCONCLUSIVO"]
    assert not page.findChild(QPushButton, "safetyStartOperationButton").isEnabled()


@pytest.mark.parametrize("detection_class", _IDS)
def test_each_ppe_alone_seen_half_the_time_is_inconclusive(qtbot, detection_class) -> None:
    page, controller, authorized = _setup(qtbot, detection_class)
    for index in range(16):
        _frame(controller, *(_boxes({detection_class}) if index % 2 else ()))
    assert authorized == []
    assert _status(page) == "AGUARDANDO ESTABILIDADE"
    name = next(item[1] for item in SUPPORTED if item[3] == detection_class)
    assert _description(page).startswith(f"Falta confirmar: {name}: ")


def test_all_supported_ppe_together_are_released(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, *_IDS)
    for _ in range(7):
        _frame(controller, *_boxes(set(_IDS)))
    assert len(authorized) == 1
    assert set(authorized[0].verified_ppe_ids) == set(range(1, 9))


@pytest.mark.parametrize("missing", _IDS)
def test_one_missing_ppe_blocks_the_combination_and_is_named(qtbot, missing) -> None:
    page, controller, authorized = _setup(qtbot, *_IDS)
    for _ in range(12):
        _frame(controller, *_boxes(set(_IDS) - {missing}))
    assert authorized == []
    name = next(item[1] for item in SUPPORTED if item[3] == missing)
    assert _description(page).startswith(f"Falta confirmar: {name}: ")
    # The UI shows the same state the engine holds for every other PPE.
    confirmed = "NA CABEÇA" if missing != "capacete" else None
    states = _states(page)
    assert states.count("CONFIRMADO") == 6 + (missing == "capacete")
    assert confirmed is None or confirmed in states


def test_ppe_not_required_never_blocks(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, "luva")
    # Helmet held in the hand and a bare-hand box: neither belongs to this operation.
    for _ in range(7):
        _frame(controller, ("luva", _BOX["luva"]), ("capacete", _HAND), ("mao_sem_luva", _HAND))
    assert len(authorized) == 1
    assert authorized[0].verified_ppe_ids == (2,)


def test_helmet_in_hand_blocks_even_with_everything_else_confirmed(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, *_IDS)
    others = _boxes(set(_IDS) - {"capacete"})
    for _ in range(10):
        _frame(controller, *others, ("capacete", _HAND))
    assert authorized == []
    assert _status(page) == "EPI AUSENTE"
    assert "NA MÃO" in _states(page)


def test_required_class_missing_from_the_model_is_named(qtbot) -> None:
    page, controller, authorized = _setup(qtbot, "luva", "mascara")
    controller._handle_model_ready(tuple(item for item in MODEL_CLASSES if item != "mascara"))
    for _ in range(7):
        _frame(controller, *_boxes({"luva", "mascara"}))
    assert authorized == []
    assert _status(page) == "SEM MAPEAMENTO"
    assert "Máscara" in _description(page)


@pytest.mark.parametrize("risk_camera", [1, 2])
def test_multicamera_selection_releases_from_the_risk_area_camera(qtbot, risk_camera) -> None:
    page = _page(qtbot, _operation("capacete", "luva", risk_camera=risk_camera))
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
    controller = _controller(page)
    controller._handle_model_ready(MODEL_CLASSES)
    authorized: list[OperationStartAuthorization] = []
    controller.operation_start_authorized.connect(authorized.append)
    for _ in range(7):
        _frame(controller, *_boxes({"capacete", "luva"}))
    assert [camera.camera_id for camera in page.selected_cameras] == [1, 2]
    assert page.verification_camera.camera_id == risk_camera
    assert len(authorized) == 1
    assert set(authorized[0].verified_ppe_ids) == {1, 2}
