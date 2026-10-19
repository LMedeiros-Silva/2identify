"""Active monitoring fuses per-camera PPE evidence before alerts and snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from PySide6.QtCore import QObject, Signal

from app.controllers.active_ppe_monitoring_controller import ActivePpeMonitoringController
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import SafetyViolationType
from app.domain.camera_source import CameraSource, CameraStatus, CameraType
from app.domain.operation import Operation, PpeRequirement
from app.domain.work_session import WorkSession, WorkSessionStatus
from app.engine import PpeRequirementSafetyState
from app.services.safety_state_service import PpeLiveState
from app.ui.active import ActiveOperationPage
from app.vision.pose import (
    COCO_KEYPOINT_COUNT,
    CocoKeypoint,
    PersonPose,
    PoseDetectionBatch,
    PoseKeypoint,
)
from app.vision.ppe import DetectionBox, PpeDetection, PpeDetectionBatch

_STARTED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
_GENERATION = 2
_HEAD = (85, 25, 115, 60)
_HAND = (60, 165, 85, 190)


class CameraControllerStub(QObject):
    analysis_frame_ready = Signal(object)
    status_changed = Signal(int, object)
    generation = _GENERATION


def _operation() -> Operation:
    return Operation(41, "Fresagem", required_ppe=(PpeRequirement(1, "Capacete", "capacete"),))


def _cameras(count: int) -> tuple[CameraSource, ...]:
    return tuple(
        CameraSource(index, f"Câmera {index}", 3, CameraType.IP) for index in range(1, count + 1)
    )


def _work_session(selected: tuple[int, ...]) -> WorkSession:
    return WorkSession(
        session_id=UUID("22222222-2222-4222-8222-222222222222"),
        operator_id=15,
        operation_id=41,
        camera_id=1,
        risk_area_id=None,
        verified_ppe_ids=(1,),
        safety_verified_at=_STARTED_AT,
        ppe_sample_count=2,
        ppe_window_size=4,
        started_at=_STARTED_AT,
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
        selected_camera_ids=selected,
    )


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
        CocoKeypoint.LEFT_ELBOW: (78, 140),
        CocoKeypoint.RIGHT_ELBOW: (122, 140),
        CocoKeypoint.LEFT_WRIST: (75, 180),
        CocoKeypoint.RIGHT_WRIST: (125, 180),
        CocoKeypoint.LEFT_HIP: (85, 220),
        CocoKeypoint.RIGHT_HIP: (115, 220),
    }.items():
        points[int(key)] = PoseKeypoint(x, y, 0.95)
    return PersonPose(0.95, tuple(points))


def _setup(qtbot, camera_count: int = 5):
    operator = OperatorSession(15, "Operador", _STARTED_AT, AuthenticationMethod.CREDENTIALS)
    page = ActiveOperationPage(operator)
    qtbot.addWidget(page)
    page.set_work_session(_work_session(tuple(range(1, camera_count + 1))), _operation())
    page.set_cameras(_cameras(camera_count))
    page.activate_monitoring()
    settings = AppSettings(
        _env_file=None,
        ppe_stability_window_frames=2,
        ppe_stability_minimum_frames=2,
        alert_minimum_consecutive_observations=2,
        alert_minimum_persistence_seconds=0,
        alert_resolution_consecutive_observations=2,
        pose_estimation_enabled=False,
    )
    controller = ActivePpeMonitoringController(settings, page, CameraControllerStub())
    controller._handle_model_ready(("capacete",))
    for camera_id in range(1, camera_count + 1):
        controller.handle_camera_status(camera_id, CameraStatus.ONLINE)
    updates: list = []
    snapshots: list = []
    controller.local_alert_update_ready.connect(updates.append)
    controller.safety_state_snapshot_ready.connect(snapshots.append)
    return page, controller, updates, snapshots


def _observe(controller, camera_id: int, helmet_box=None, *, with_person: bool = True) -> None:
    captured_at = datetime.now(UTC)
    detections = (
        (PpeDetection(0, "capacete", 0.94, DetectionBox(*helmet_box)),)
        if helmet_box is not None
        else ()
    )
    if with_person:
        controller.handle_pose_batch(
            PoseDetectionBatch((_person(),), 640, 480, 1.0, camera_id, _GENERATION, captured_at)
        )
    controller._handle_detections(
        PpeDetectionBatch(detections, 640, 480, 1.0, camera_id, _GENERATION, captured_at)
    )


def _cycle(controller, boxes: dict[int, tuple | None], rounds: int = 4) -> None:
    for _ in range(rounds):
        for camera_id, box in boxes.items():
            _observe(controller, camera_id, box, with_person=box is not None)


def _ppe_absent(updates) -> list:
    return [
        alert
        for update in updates
        for alert in update.raised_alerts
        if alert.violation.violation_type is SafetyViolationType.PPE_ABSENT
    ]


def test_scenario_a_one_camera_present_four_unknown_no_alert_and_admin_sees_confirmed(
    qtbot,
) -> None:
    page, controller, updates, snapshots = _setup(qtbot)

    _cycle(controller, {1: None, 2: None, 3: None, 4: None, 5: _HEAD})

    fusion = controller._latest_fusion
    assert fusion is not None
    decision = fusion.decision_for(1)
    assert decision.state is PpeRequirementSafetyState.CONFIRMED
    assert decision.present_camera_ids == (5,)
    assert _ppe_absent(updates) == []
    assert page.active_alert_count == 0
    # The primary camera (1) never saw the helmet; the Admin/ESP32 snapshot is fused.
    assert snapshots[-1].ppe[0].state is PpeLiveState.CONFIRMED
    controller.shutdown()
    page.clear()


def test_scenario_b_single_camera_confirmed_absence_raises_alert_on_that_camera(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot)

    _cycle(controller, {1: None, 2: None, 3: _HAND, 4: None, 5: None})

    alerts = _ppe_absent(updates)
    assert len(alerts) == 1
    assert alerts[0].camera_id == 3
    assert snapshots[-1].ppe[0].state is PpeLiveState.ABSENT
    controller.shutdown()
    page.clear()


def test_scenario_c_all_unknown_never_becomes_absence(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot)

    _cycle(controller, dict.fromkeys(range(1, 6)), rounds=6)

    assert _ppe_absent(updates) == []
    assert snapshots[-1].ppe[0].state in {PpeLiveState.COLLECTING, PpeLiveState.UNSTABLE}
    controller.shutdown()
    page.clear()


def test_scenario_d_simultaneous_conflict_is_unknown_without_alert(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot)

    _cycle(controller, {1: None, 2: _HEAD, 3: _HAND, 4: None, 5: None})

    decision = controller._latest_fusion.decision_for(1)
    assert decision.conflict
    assert decision.state is PpeRequirementSafetyState.UNSTABLE
    assert _ppe_absent(updates) == []
    assert snapshots[-1].ppe[0].state is PpeLiveState.UNSTABLE
    controller.shutdown()
    page.clear()


def test_absence_alert_resolves_when_another_camera_confirms_later(qtbot) -> None:
    page, controller, updates, _ = _setup(qtbot, camera_count=2)

    _cycle(controller, {1: None, 2: _HAND})
    assert len(_ppe_absent(updates)) == 1

    _cycle(controller, {1: _HEAD, 2: None}, rounds=6)

    resolved = [alert for update in updates for alert in update.resolved_alerts]
    assert [alert.camera_id for alert in resolved] == [2]
    assert page.active_alert_count == 0
    controller.shutdown()
    page.clear()


def test_offline_camera_evidence_leaves_the_fusion(qtbot) -> None:
    page, controller, _, snapshots = _setup(qtbot, camera_count=2)

    _cycle(controller, {1: None, 2: _HEAD})
    assert controller._latest_fusion.decision_for(1).present_camera_ids == (2,)

    controller.handle_camera_status(2, CameraStatus.OFFLINE)

    assert controller._latest_fusion.decision_for(1).present_camera_ids == ()
    assert snapshots[-1].ppe[0].state is not PpeLiveState.CONFIRMED
    controller.shutdown()
    page.clear()


def test_multicamera_status_line_follows_the_fused_assessment(qtbot) -> None:
    page, controller, _, _ = _setup(qtbot, camera_count=3)

    _cycle(controller, {1: None, 2: None, 3: _HEAD})

    assert page._monitoring_status.text() == "EPIs CONFIRMADOS"
    controller.shutdown()
    page.clear()
