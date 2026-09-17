from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QCheckBox, QLabel, QScrollArea

from app.controllers.active_ergonomics_monitoring_controller import (
    ActiveErgonomicsMonitoringController,
)
from app.controllers.active_ppe_monitoring_controller import ActivePpeMonitoringController
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSession
from app.domain.camera_source import CameraSource, CameraStatus, CameraType
from app.domain.operation import Operation, PpeRequirement, RiskAreaReference
from app.domain.risk_area import NormalizedPoint, RiskAreaGeometry
from app.domain.work_session import WorkSession, WorkSessionStatus
from app.engine.ppe_safety import PpeEvidenceState
from app.services.safety_state_service import PpeLiveState, SafetyStateSnapshot
from app.ui.active import ActiveOperationPage
from app.ui.components import CameraFrameView
from app.ui.safety import SafetyVerificationPage
from app.vision.pose import PoseDetectionBatch
from app.vision.ppe import DetectionBox, PpeDetection, PpeDetectionBatch

_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _operator() -> OperatorSession:
    return OperatorSession(15, "Operador", _NOW, AuthenticationMethod.CREDENTIALS)


def _operation() -> Operation:
    geometry = RiskAreaGeometry(
        (
            NormalizedPoint(0.1, 0.1),
            NormalizedPoint(0.8, 0.1),
            NormalizedPoint(0.5, 0.8),
        )
    )
    return Operation(
        41,
        "Operação multicâmera",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
        risk_area=RiskAreaReference(7, "Área A", geometry, True, 1, "Câmera 1"),
    )


def _cameras(count: int = 5) -> tuple[CameraSource, ...]:
    return tuple(
        CameraSource(
            camera_id=index,
            name=f"Câmera {index}",
            sector_id=3,
            source_type=CameraType.USB if index >= 4 else CameraType.IP,
        )
        for index in range(1, count + 1)
    )


class CameraControllerStub(QObject):
    analysis_frame_ready = Signal(object)
    status_changed = Signal(int, object)
    generation = 2


def _work_session(selected: tuple[int, ...]) -> WorkSession:
    return WorkSession(
        session_id=UUID("11111111-1111-4111-8111-111111111111"),
        operator_id=15,
        operation_id=41,
        camera_id=1,
        risk_area_id=7,
        verified_ppe_ids=(1,),
        safety_verified_at=_NOW,
        ppe_sample_count=2,
        ppe_window_size=4,
        started_at=_NOW,
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
        selected_camera_ids=selected,
    )


@pytest.mark.parametrize(
    ("available_count", "selected_count"),
    [(5, 1), (5, 3), (5, 4), (5, 5), (6, 4), (6, 6)],
)
def test_selects_any_nonempty_subset_before_monitoring(
    qtbot, available_count: int, selected_count: int
) -> None:
    page = SafetyVerificationPage(_operator())
    qtbot.addWidget(page)
    page.enable_multicamera_catalog()
    page.set_operation(_operation())
    with qtbot.waitSignal(page.catalog_requested, timeout=1_000) as requested:
        page.activate()
    assert requested.args == [41]
    page.set_cameras(41, _cameras(available_count))
    for index in range(1, available_count + 1):
        check = page.findChild(QCheckBox, f"safetyCameraChoice_{index}")
        check.setChecked(index <= selected_count)
    with qtbot.waitSignal(page.camera_start_requested, timeout=1_000):
        page._begin_selected_monitoring()
    assert tuple(item.camera_id for item in page.selected_cameras) == tuple(
        range(1, selected_count + 1)
    )
    assert page.verification_camera.camera_id == 1
    page.deactivate()


def test_selection_can_skip_unavailable_cameras_without_removing_them_from_catalog(qtbot) -> None:
    page = SafetyVerificationPage(_operator())
    qtbot.addWidget(page)
    page.enable_multicamera_catalog()
    page.set_operation(_operation())
    page.activate()
    page.set_cameras(41, _cameras(6))
    for camera_id in range(1, 7):
        check = page.findChild(QCheckBox, f"safetyCameraChoice_{camera_id}")
        check.setChecked(camera_id in {1, 2, 3, 6})
    with qtbot.waitSignal(page.camera_start_requested, timeout=1_000):
        page._begin_selected_monitoring()
    assert tuple(item.camera_id for item in page.selected_cameras) == (1, 2, 3, 6)
    assert not page.findChild(QCheckBox, "safetyCameraChoice_4").isChecked()
    assert not page.findChild(QCheckBox, "safetyCameraChoice_5").isChecked()
    page.deactivate()


@pytest.mark.parametrize("camera_count", [1, 2, 3, 4, 5, 6])
def test_active_grid_has_one_named_visible_tile_per_selected_camera(qtbot, camera_count) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.resize(1100, 700)
    page.set_work_session(_work_session(tuple(range(1, camera_count + 1))), _operation())
    page.set_cameras(_cameras(camera_count))
    page.activate_monitoring()

    scroll = page.findChild(QScrollArea, "activeCameraGridScroll")
    assert scroll is not None and scroll.widgetResizable() and not scroll.isHidden()
    assert page._camera_grid.count() == camera_count
    assert set(page._camera_tiles) == set(range(1, camera_count + 1))
    for camera_id in range(1, camera_count + 1):
        tile = page._tile_containers[camera_id]
        assert page._camera_grid.indexOf(tile) >= 0
        assert tile.findChild(QLabel, "activeCameraTileName").text() == f"Câmera {camera_id}"
        assert page._tile_statuses[camera_id].text() == "CONNECTING"
    page.clear()


def test_frames_are_routed_only_to_their_camera_tiles(qtbot) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.set_work_session(_work_session((1, 2)), _operation())
    page.set_cameras(_cameras(2))
    page.activate_monitoring()
    red = QImage(48, 32, QImage.Format.Format_RGB888)
    red.fill(QColor("red"))
    blue = QImage(48, 32, QImage.Format.Format_RGB888)
    blue.fill(QColor("blue"))

    page.update_camera_tile(1, red)
    assert page._camera_tiles[1]._frame.pixelColor(0, 0) == QColor("red")
    assert not page._camera_tiles[2].has_frame
    page.update_camera_tile(2, blue)
    assert page._camera_tiles[1]._frame.pixelColor(0, 0) == QColor("red")
    assert page._camera_tiles[2]._frame.pixelColor(0, 0) == QColor("blue")
    page.clear()


def test_offline_camera_stays_in_four_tile_grid_while_others_update(qtbot) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.set_work_session(_work_session((1, 2, 3, 4)), _operation())
    page.set_cameras(_cameras(4))
    page.activate_monitoring()
    frame = QImage(48, 32, QImage.Format.Format_RGB888)
    frame.fill(QColor("green"))
    for camera_id in (1, 2, 3, 4):
        page.set_camera_tile_status(camera_id, CameraStatus.ONLINE)
        page.update_camera_tile(camera_id, frame)
    page.set_camera_tile_status(3, CameraStatus.OFFLINE)

    assert page._camera_grid.count() == 4
    assert page._tile_statuses[3].text() == "OFFLINE"
    assert not page._camera_tiles[3].has_frame
    for camera_id in (1, 2, 4):
        page.update_camera_tile(camera_id, frame)
        assert page._camera_tiles[camera_id].has_frame
        assert page._tile_statuses[camera_id].text() == "ONLINE"
    page.clear()


def test_new_selection_removes_old_tiles_and_ignores_late_camera_frames(qtbot) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.set_work_session(_work_session((1, 2, 3)), _operation())
    page.set_cameras(_cameras(3))
    page.activate_monitoring()
    old = QImage(48, 32, QImage.Format.Format_RGB888)
    old.fill(QColor("red"))
    page.update_camera_tile(2, old)
    page.clear()

    page.set_work_session(_work_session((1, 4)), _operation())
    page.set_cameras((_cameras(4)[0], _cameras(4)[3]))
    page.activate_monitoring()
    page.update_camera_tile(2, old)
    page.update_camera_tile(3, old)
    assert set(page._camera_tiles) == {1, 4}
    assert page._camera_grid.count() == 2
    assert not page._camera_tiles[1].has_frame
    assert not page._camera_tiles[4].has_frame
    page.clear()


@pytest.mark.parametrize("camera_count", [5, 6])
def test_active_grid_keeps_frames_status_and_risk_zone_on_own_camera(
    qtbot, camera_count: int
) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    work_session = _work_session(tuple(range(1, camera_count + 1)))
    page.set_work_session(work_session, _operation())
    page.set_cameras(_cameras(camera_count))
    page.activate_monitoring()
    views = tuple(
        page.findChild(CameraFrameView, f"activeCameraTilePreview_{index}")
        for index in range(1, camera_count + 1)
    )
    assert all(view is not None for view in views)
    assert [view.risk_zone_count for view in views] == [1] + [0] * (camera_count - 1)
    frame = QImage(48, 32, QImage.Format.Format_RGB888)
    for camera_id in range(1, camera_count + 1):
        page.update_camera_tile(camera_id, frame)
    assert all(view.has_frame for view in views)
    page.set_camera_tile_status(1, CameraStatus.OFFLINE)
    page.set_camera_tile_status(2, CameraStatus.ONLINE)
    assert not views[0].has_frame
    assert all(view.has_frame for view in views[1:])
    assert page.findChild(QLabel, "activeCameraTileStatus_1").text() == "OFFLINE"
    assert page.findChild(QLabel, "activeCameraTileStatus_2").text() == "ONLINE"
    assert page.findChild(QLabel, "activeCameraStatus").text() == f"1/{camera_count} ONLINE"
    page.clear()


def test_ppe_stability_is_independent_for_each_camera_and_offline_becomes_unknown(qtbot) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.set_work_session(_work_session((1, 2)), _operation())
    page.set_cameras(_cameras()[:2])
    page.activate_monitoring()
    camera = CameraControllerStub()
    settings = AppSettings(
        _env_file=None,
        ppe_stability_window_frames=2,
        ppe_stability_minimum_frames=2,
        ppe_stability_present_ratio=0.75,
        ppe_stability_absent_ratio=0.25,
        pose_estimation_enabled=False,
    )
    controller = ActivePpeMonitoringController(settings, page, camera)
    controller._handle_model_ready(("capacete",))
    present = (PpeDetection(0, "capacete", 0.9, DetectionBox(1, 1, 8, 8)),)
    for _ in range(2):
        for camera_id, detections in ((1, present), (2, ())):
            controller._handle_detections(
                PpeDetectionBatch(
                    detections,
                    48,
                    32,
                    1.0,
                    camera_id=camera_id,
                    generation=2,
                    captured_at=datetime.now(UTC),
                )
            )
    assert controller._assessment_by_camera[1].requirements[0].evidence is PpeEvidenceState.UNKNOWN
    assert controller._assessment_by_camera[2].requirements[0].evidence is PpeEvidenceState.UNKNOWN
    assert page.findChild(QLabel, "activeCameraTilePpe_1").text() == "Capacete: VERIFICANDO"
    assert page.findChild(QLabel, "activeCameraTilePpe_2").text() == "Capacete: VERIFICANDO"
    assert page.active_alert_count == 0
    camera.status_changed.emit(1, CameraStatus.OFFLINE)
    assert 1 not in controller._assessment_by_camera
    assert "UNKNOWN" in page.findChild(QLabel, "activeCameraTilePpe_1").text()
    controller._handle_detections(
        PpeDetectionBatch(
            present, 48, 32, 1.0, camera_id=1, generation=2, captured_at=datetime.now(UTC)
        )
    )
    assert 1 not in controller._assessment_by_camera
    controller.shutdown()
    page.clear()


def test_inference_failure_invalidates_camera_ppe_evidence(qtbot) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.set_work_session(_work_session((1,)), _operation())
    page.set_cameras(_cameras()[:1])
    page.activate_monitoring()
    camera = CameraControllerStub()
    settings = AppSettings(
        _env_file=None,
        ppe_stability_window_frames=1,
        ppe_stability_minimum_frames=1,
    )
    controller = ActivePpeMonitoringController(settings, page, camera)
    controller._handle_model_ready(("capacete",))
    controller._handle_detections(
        PpeDetectionBatch(
            (PpeDetection(0, "capacete", 0.9, DetectionBox(1, 1, 8, 8)),),
            48, 32, 1.0, camera_id=1, generation=2, captured_at=datetime.now(UTC),
        )
    )
    assert "VERIFICANDO" in page.findChild(QLabel, "activeCameraTilePpe_1").text()
    controller._handle_failure("Modelo indisponível", True)
    assert "UNKNOWN" in page.findChild(QLabel, "activeCameraTilePpe_1").text()
    controller.shutdown()
    page.clear()


def test_pose_never_uses_primary_risk_polygon_on_second_camera(qtbot) -> None:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.set_work_session(_work_session((1, 2)), _operation())
    page.set_cameras(_cameras()[:2])
    page.activate_monitoring()
    camera = CameraControllerStub()
    controller = ActiveErgonomicsMonitoringController(
        AppSettings(_env_file=None), page, camera
    )
    controller._model_ready = True
    observed = []
    controller.risk_area_assessment_ready.connect(observed.append)
    controller._handle_poses(PoseDetectionBatch((), 48, 32, 1.0, camera_id=2, generation=2))
    assert observed == []
    controller._handle_poses(PoseDetectionBatch((), 48, 32, 1.0, camera_id=1, generation=2))
    assert len(observed) == 1
    assert observed[0].camera_id == 1
    camera.status_changed.emit(1, CameraStatus.OFFLINE)
    controller._handle_poses(PoseDetectionBatch((), 48, 32, 1.0, camera_id=1, generation=2))
    assert len(observed) == 1
    controller.shutdown()
    page.clear()


def test_legacy_tower_snapshot_stays_unknown_without_primary_camera_evidence() -> None:
    snapshot = SafetyStateSnapshot.from_alerts(
        _work_session((2,)), (), _NOW, operation=_operation()
    )
    assert snapshot.camera_id == 1
    assert tuple(item.state for item in snapshot.ppe) == (PpeLiveState.COLLECTING,)
    assert snapshot.started_at == _NOW
