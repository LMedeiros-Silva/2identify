"""Prolonged UNKNOWN PPE evidence is a MEDIUM monitoring condition, never an absence."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from PySide6.QtCore import QObject, Signal

from app.api.client import OperatorApiClient
from app.controllers.active_ppe_monitoring_controller import ActivePpeMonitoringController
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import SafetyAlertSeverity, SafetyViolationType
from app.domain.camera_source import CameraSource, CameraStatus, CameraType
from app.domain.operation import Operation, PpeRequirement
from app.domain.work_session import WorkSession, WorkSessionStatus
from app.services.safety_state_service import PpeLiveState, SafetyStateReason
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
_TOLERANCE = 0.3
_INCONCLUSIVE = SafetyViolationType.MONITORING_INTERRUPTED


class CameraControllerStub(QObject):
    analysis_frame_ready = Signal(object)
    status_changed = Signal(int, object)
    generation = _GENERATION


def _operation(with_gloves: bool = False) -> Operation:
    required = [PpeRequirement(1, "Capacete", "capacete")]
    if with_gloves:
        required.append(PpeRequirement(2, "Luva", "luva"))
    return Operation(41, "Fresagem", required_ppe=tuple(required))


def _work_session(selected: tuple[int, ...]) -> WorkSession:
    return WorkSession(
        session_id=UUID("33333333-3333-4333-8333-333333333333"),
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


def _setup(
    qtbot,
    camera_count: int = 5,
    *,
    with_gloves: bool = False,
    tolerance: float | None = _TOLERANCE,
    **overrides,
):
    operator = OperatorSession(15, "Operador", _STARTED_AT, AuthenticationMethod.CREDENTIALS)
    page = ActiveOperationPage(operator)
    qtbot.addWidget(page)
    page.set_work_session(_work_session(tuple(range(1, camera_count + 1))), _operation(with_gloves))
    page.set_cameras(
        tuple(
            CameraSource(index, f"Câmera {index}", 3, CameraType.IP)
            for index in range(1, camera_count + 1)
        )
    )
    page.activate_monitoring()
    settings = AppSettings(
        _env_file=None,
        ppe_stability_window_frames=2,
        ppe_stability_minimum_frames=2,
        alert_minimum_consecutive_observations=2,
        alert_minimum_persistence_seconds=0,
        alert_resolution_consecutive_observations=2,
        alert_critical_after_seconds=0.2,
        pose_estimation_enabled=False,
        ppe_inconclusive_tolerance_seconds=tolerance,
        **overrides,
    )
    controller = ActivePpeMonitoringController(settings, page, CameraControllerStub())
    controller._handle_model_ready(("capacete", "luva") if with_gloves else ("capacete",))
    for camera_id in range(1, camera_count + 1):
        controller.handle_camera_status(camera_id, CameraStatus.ONLINE)
    updates: list = []
    snapshots: list = []
    controller.local_alert_update_ready.connect(updates.append)
    controller.safety_state_snapshot_ready.connect(snapshots.append)
    return page, controller, updates, snapshots


def _observe(
    controller,
    camera_id: int,
    helmet_box=None,
    *,
    captured_at: datetime | None = None,
    gloves: bool = False,
) -> None:
    captured_at = captured_at or datetime.now(UTC)
    detections = []
    if helmet_box is not None:
        detections.append(PpeDetection(0, "capacete", 0.94, DetectionBox(*helmet_box)))
    if gloves:
        detections.append(PpeDetection(1, "luva", 0.93, DetectionBox(70, 170, 90, 195)))
    if helmet_box is not None:
        controller.handle_pose_batch(
            PoseDetectionBatch((_person(),), 640, 480, 1.0, camera_id, _GENERATION, captured_at)
        )
    controller._handle_detections(
        PpeDetectionBatch(tuple(detections), 640, 480, 1.0, camera_id, _GENERATION, captured_at)
    )


def _cycle(controller, boxes: dict[int, tuple | None], rounds: int = 4, **kwargs) -> None:
    for _ in range(rounds):
        for camera_id, box in boxes.items():
            _observe(controller, camera_id, box, **kwargs)


def _hold(controller, boxes: dict[int, tuple | None], seconds: float, **kwargs) -> None:
    """Keep the cameras reporting the same scene for a wall-clock interval."""

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _cycle(controller, boxes, rounds=1, **kwargs)
        time.sleep(0.02)
    _cycle(controller, boxes, rounds=3, **kwargs)


def _raised(updates, violation_type) -> list:
    return [
        alert
        for update in updates
        for alert in update.raised_alerts
        if alert.violation.violation_type is violation_type
    ]


def _resolved(updates, violation_type) -> list:
    return [
        alert
        for update in updates
        for alert in update.resolved_alerts
        if alert.violation.violation_type is violation_type
    ]


def _active(updates) -> tuple:
    return updates[-1].active_alerts if updates else ()


def _close(controller, page) -> None:
    controller.shutdown()
    page.clear()


def test_four_unknown_and_one_present_with_staggered_timestamps_is_not_inconclusive(
    qtbot,
) -> None:
    page, controller, updates, snapshots = _setup(qtbot)

    deadline = time.monotonic() + _TOLERANCE * 3
    while time.monotonic() < deadline:
        base = datetime.now(UTC)
        for camera_id in range(1, 6):
            # Each camera delivers a frame captured at a different moment.
            captured_at = base - timedelta(milliseconds=40 * (5 - camera_id))
            box = _HEAD if camera_id == 5 else None
            _observe(controller, camera_id, box, captured_at=captured_at)
        time.sleep(0.02)

    assert controller._latest_fusion.decision_for(1).present_camera_ids == (5,)
    assert _raised(updates, _INCONCLUSIVE) == []
    assert _raised(updates, SafetyViolationType.PPE_ABSENT) == []
    assert snapshots[-1].ppe[0].state is PpeLiveState.CONFIRMED
    _close(controller, page)


def test_four_unknown_and_one_confirmed_absence_is_a_real_violation(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot)

    _hold(controller, {1: None, 2: None, 3: _HAND, 4: None, 5: None}, _TOLERANCE * 2)

    absent = _raised(updates, SafetyViolationType.PPE_ABSENT)
    assert len(absent) == 1
    assert absent[0].camera_id == 3
    assert _raised(updates, _INCONCLUSIVE) == []
    assert snapshots[-1].ppe[0].state is PpeLiveState.ABSENT
    assert [item.reason for item in snapshots[-1].conditions] == [SafetyStateReason.PPE_MISSING]
    _close(controller, page)


def test_five_prolonged_unknown_is_inconclusive_medium_and_never_absent(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot)

    _hold(controller, dict.fromkeys(range(1, 6)), _TOLERANCE * 3)

    inconclusive = _raised(updates, _INCONCLUSIVE)
    assert len(inconclusive) == 1
    alert = inconclusive[0]
    assert alert.violation.subject_key == "ppe_inconclusive:1"
    assert alert.violation.ppe_id == 1
    assert alert.violation.summary == "Monitoramento de EPI inconclusivo: Capacete"
    # MEDIUM: it does not escalate even after ALERT_CRITICAL_AFTER_SECONDS.
    assert alert.violation.severity is SafetyAlertSeverity.WARNING
    assert all(
        item.violation.severity is SafetyAlertSeverity.WARNING
        for item in _active(updates)
        if item.violation.violation_type is _INCONCLUSIVE
    )
    assert not any(update.escalated_alerts for update in updates)
    assert _raised(updates, SafetyViolationType.PPE_ABSENT) == []
    assert snapshots[-1].ppe[0].state in {PpeLiveState.COLLECTING, PpeLiveState.UNSTABLE}
    assert page.active_alert_count == 1
    _close(controller, page)


def test_momentary_loss_of_evidence_raises_nothing(qtbot) -> None:
    page, controller, updates, _ = _setup(qtbot, camera_count=2, tolerance=1.0)

    for _ in range(3):
        _hold(controller, {1: None, 2: _HEAD}, 0.25)
        # The helmet leaves the only view that saw it, then comes back quickly.
        _hold(controller, {1: None, 2: None}, 0.2)
    _hold(controller, {1: None, 2: _HEAD}, 0.25)

    assert _raised(updates, _INCONCLUSIVE) == []
    assert _raised(updates, SafetyViolationType.PPE_ABSENT) == []
    _close(controller, page)


def test_inconclusive_resolves_automatically_when_reliable_evidence_returns(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot, camera_count=3)

    _hold(controller, {1: None, 2: None, 3: None}, _TOLERANCE * 2)
    assert len(_raised(updates, _INCONCLUSIVE)) == 1

    _cycle(controller, {1: None, 2: _HEAD, 3: None}, rounds=4)

    resolved = _resolved(updates, _INCONCLUSIVE)
    assert len(resolved) == 1
    assert resolved[0].alert_id == _raised(updates, _INCONCLUSIVE)[0].alert_id
    assert page.active_alert_count == 0
    assert snapshots[-1].ppe[0].state is PpeLiveState.CONFIRMED
    assert snapshots[-1].conditions == ()
    _close(controller, page)


def test_critical_absence_and_inconclusive_item_coexist_and_critical_prevails(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot, camera_count=2, with_gloves=True)

    # Helmet confirmed absent (in the hand) by camera 2; no camera ever sees the gloves.
    _hold(controller, {1: None, 2: _HAND}, _TOLERANCE * 3)

    severities = {
        item.violation.violation_type: item.violation.severity for item in _active(updates)
    }
    assert severities == {
        SafetyViolationType.PPE_ABSENT: SafetyAlertSeverity.CRITICAL,
        _INCONCLUSIVE: SafetyAlertSeverity.WARNING,
    }
    inconclusive = _raised(updates, _INCONCLUSIVE)
    assert [item.violation.ppe_id for item in inconclusive] == [2]
    # The snapshot carries the critical condition; the tower takes the highest level.
    assert [(item.reason, item.level.value) for item in snapshots[-1].conditions] == [
        (SafetyStateReason.PPE_MISSING, "critical")
    ]
    _close(controller, page)


def test_offline_camera_does_not_keep_old_evidence(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot, camera_count=2)

    _hold(controller, {1: None, 2: _HEAD}, _TOLERANCE * 1.5)
    assert _raised(updates, _INCONCLUSIVE) == []

    controller.handle_camera_status(2, CameraStatus.OFFLINE)
    _hold(controller, {1: None}, _TOLERANCE * 2)

    assert len(_raised(updates, _INCONCLUSIVE)) == 1
    assert snapshots[-1].ppe[0].state is not PpeLiveState.CONFIRMED
    _close(controller, page)


def test_expired_evidence_from_a_silent_camera_stops_counting(qtbot) -> None:
    page, controller, updates, _ = _setup(
        qtbot, camera_count=2, ppe_fusion_evidence_max_age_seconds=0.2
    )

    _cycle(controller, {1: None, 2: _HEAD})
    assert controller._latest_fusion.decision_for(1).present_camera_ids == (2,)
    # Camera 2 stops sending frames without any status change; camera 1 keeps running.
    _hold(controller, {1: None}, _TOLERANCE * 2)

    assert controller._latest_fusion.decision_for(1).observing_camera_ids == (1,)
    assert len(_raised(updates, _INCONCLUSIVE)) == 1
    _close(controller, page)


def test_inconclusive_is_raised_even_when_no_frame_arrives(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot, camera_count=2)

    deadline = time.monotonic() + _TOLERANCE * 2
    while time.monotonic() < deadline:
        controller._expire_stale_cameras()
        time.sleep(0.03)
    for _ in range(3):
        controller._expire_stale_cameras()

    assert len(_raised(updates, _INCONCLUSIVE)) == 1
    assert snapshots[-1].ppe[0].state is PpeLiveState.COLLECTING
    _close(controller, page)


def test_single_webcam_inconclusive_and_recovery(qtbot) -> None:
    page, controller, updates, _ = _setup(qtbot, camera_count=1)

    _hold(controller, {1: None}, _TOLERANCE * 2)
    assert len(_raised(updates, _INCONCLUSIVE)) == 1

    _cycle(controller, {1: _HEAD})

    assert len(_resolved(updates, _INCONCLUSIVE)) == 1
    assert page.active_alert_count == 0
    _close(controller, page)


def test_stopping_the_operation_clears_the_timers(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot, camera_count=1)
    _hold(controller, {1: None}, _TOLERANCE * 2)
    assert len(_raised(updates, _INCONCLUSIVE)) == 1

    controller.stop()
    assert controller._ppe_unknown_since == {}
    assert controller._session_alert_engine.active_alerts == ()
    assert snapshots[-1].conditions == ()
    updates.clear()

    # The next operation starts counting from zero.
    controller._handle_model_ready(("capacete",))
    controller.handle_camera_status(1, CameraStatus.ONLINE)
    _cycle(controller, {1: None})

    assert _raised(updates, _INCONCLUSIVE) == []
    _close(controller, page)


def test_several_cameras_confirming_the_same_absence_raise_one_alert(qtbot) -> None:
    page, controller, updates, snapshots = _setup(qtbot, camera_count=3)

    _cycle(controller, {1: None, 2: _HAND, 3: None})
    _cycle(controller, {1: _HAND, 2: _HAND, 3: _HAND})
    # The original evidence camera loses sight; the others keep confirming.
    _cycle(controller, {1: _HAND, 2: None, 3: _HAND}, rounds=6)

    absent = _raised(updates, SafetyViolationType.PPE_ABSENT)
    assert len(absent) == 1
    assert absent[0].camera_id == 2
    assert _resolved(updates, SafetyViolationType.PPE_ABSENT) == []
    assert [item.condition_id for item in snapshots[-1].conditions] == ["ppe_absent:ppe:1"]
    _close(controller, page)


def test_default_tolerance_follows_the_window_and_per_camera_rate(qtbot) -> None:
    single_page, single, _, _ = _setup(qtbot, camera_count=1, tolerance=None)
    multi_page, multi, _, _ = _setup(qtbot, camera_count=5, tolerance=None)

    # Window of 2 frames at 4 FPS shared by the selected cameras, twice.
    assert single._inconclusive_tolerance() == timedelta(seconds=1)
    assert multi._inconclusive_tolerance() == timedelta(seconds=5)
    assert AppSettings(_env_file=None).ppe_inconclusive_tolerance_seconds is None
    _close(single, single_page)
    _close(multi, multi_page)


def test_inconclusive_alert_payload_is_the_monitoring_contract_the_api_accepts(qtbot) -> None:
    page, controller, updates, _ = _setup(qtbot, camera_count=1)
    _hold(controller, {1: None}, _TOLERANCE * 2)
    alert = _raised(updates, _INCONCLUSIVE)[0]
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(
            201,
            json={
                "event_id": body["event_id"],
                "alert_id": 9,
                "occurrence_id": 9,
                "duplicate": False,
            },
        )

    client = OperatorApiClient(
        base_url="https://api.example.test/v1",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=2.0,
        transport=httpx.MockTransport(handler),
    )
    client.send_alert(alert, "token")

    assert sent[0]["violation_type"] == "monitoring_interrupted"
    assert sent[0]["severity"] == "warning"
    assert sent[0]["subject_key"] == "ppe_inconclusive:1"
    assert sent[0]["camera_id"] == 1
    _close(controller, page)
