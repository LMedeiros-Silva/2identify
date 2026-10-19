"""Fall detection through the real Pose and monitoring controllers."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from PySide6.QtCore import QObject, Signal

from app.api.client import OperatorApiClient
from app.controllers.active_ergonomics_monitoring_controller import (
    ActiveErgonomicsMonitoringController,
)
from app.controllers.active_ppe_monitoring_controller import ActivePpeMonitoringController
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import SafetyAlertSeverity, SafetyViolationType
from app.domain.camera_source import CameraSource, CameraStatus, CameraType
from app.domain.operation import Operation, PpeRequirement
from app.domain.work_session import WorkSession, WorkSessionStatus
from app.services.safety_state_service import SafetyStateLevel, SafetyStateReason
from app.ui.active import ActiveOperationPage
from app.vision.pose import PoseDetectionBatch
from tests.unit.engine.test_fall import BENDING, LYING, SQUAT, STANDING

_STARTED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
_GENERATION = 2
_FALL = SafetyViolationType.FALL_DETECTED


class CameraControllerStub(QObject):
    analysis_frame_ready = Signal(object)
    status_changed = Signal(int, object)
    generation = _GENERATION


def _setup(qtbot, camera_count: int = 1):
    operator = OperatorSession(15, "Operador", _STARTED_AT, AuthenticationMethod.CREDENTIALS)
    page = ActiveOperationPage(operator)
    qtbot.addWidget(page)
    selected = tuple(range(1, camera_count + 1))
    page.set_work_session(
        WorkSession(
            session_id=UUID("44444444-4444-4444-8444-444444444444"),
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
        ),
        Operation(41, "Fresagem", required_ppe=(PpeRequirement(1, "Capacete", "capacete"),)),
    )
    page.set_cameras(
        tuple(CameraSource(index, f"Câmera {index}", 3, CameraType.USB) for index in selected)
    )
    page.activate_monitoring()
    settings = AppSettings(
        _env_file=None,
        alert_minimum_consecutive_observations=2,
        alert_minimum_persistence_seconds=0,
        alert_resolution_consecutive_observations=2,
        fall_confirmation_seconds=0.3,
        fall_recovery_seconds=0.3,
        fall_evidence_gap_seconds=0.5,
    )
    camera = CameraControllerStub()
    monitoring = ActivePpeMonitoringController(settings, page, camera)
    pose = ActiveErgonomicsMonitoringController(settings, page, camera)
    pose._handle_model_ready()
    pose.assessment_ready.connect(monitoring.handle_ergonomic_assessment)
    for camera_id in selected:
        monitoring.handle_camera_status(camera_id, CameraStatus.ONLINE)
        pose.handle_camera_status(camera_id, CameraStatus.ONLINE)
    updates: list = []
    snapshots: list = []
    monitoring.local_alert_update_ready.connect(updates.append)
    monitoring.safety_state_snapshot_ready.connect(snapshots.append)
    return page, monitoring, pose, updates, snapshots


def _hold(pose, scenes: dict[int, object], seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        for camera_id, person in scenes.items():
            poses = (person,) if person is not None else ()
            pose._handle_poses(
                PoseDetectionBatch(poses, 640, 480, 1.0, camera_id, _GENERATION, datetime.now(UTC))
            )
        if time.monotonic() >= deadline:
            return
        time.sleep(0.03)


def _raised(updates) -> list:
    return [
        alert
        for update in updates
        for alert in update.raised_alerts
        if alert.violation.violation_type is _FALL
    ]


def _resolved(updates) -> list:
    return [
        alert
        for update in updates
        for alert in update.resolved_alerts
        if alert.violation.violation_type is _FALL
    ]


def _close(page, monitoring, pose) -> None:
    pose.shutdown()
    monitoring.shutdown()
    page.clear()


def test_confirmed_fall_is_critical_red_and_recovers_with_stable_upright_posture(qtbot) -> None:
    page, monitoring, pose, updates, snapshots = _setup(qtbot)

    _hold(pose, {1: STANDING}, 0.2)
    _hold(pose, {1: LYING}, 0.6)

    raised = _raised(updates)
    assert len(raised) == 1
    assert raised[0].violation.severity is SafetyAlertSeverity.CRITICAL
    assert raised[0].camera_id == 1
    # Critical from the first notification: the tower goes RED immediately.
    assert (SafetyStateReason.FALL_DETECTED, SafetyStateLevel.CRITICAL) in {
        (item.reason, item.level) for item in snapshots[-1].conditions
    }
    assert not any(update.escalated_alerts for update in updates)

    _hold(pose, {1: STANDING}, 0.6)

    assert [alert.alert_id for alert in _resolved(updates)] == [raised[0].alert_id]
    assert snapshots[-1].conditions == ()
    _close(page, monitoring, pose)


def test_squatting_or_bending_does_not_raise_a_fall(qtbot) -> None:
    page, monitoring, pose, updates, _ = _setup(qtbot)

    _hold(pose, {1: SQUAT}, 0.6)
    _hold(pose, {1: BENDING}, 0.6)
    _hold(pose, {1: None}, 0.3)

    assert _raised(updates) == []
    _close(page, monitoring, pose)


def test_a_fall_seen_by_two_cameras_is_one_alert(qtbot) -> None:
    page, monitoring, pose, updates, snapshots = _setup(qtbot, camera_count=2)

    _hold(pose, {1: LYING, 2: None}, 0.5)
    _hold(pose, {1: LYING, 2: LYING}, 0.5)
    # The first camera loses the person; the second keeps confirming.
    _hold(pose, {1: None, 2: LYING}, 0.5)

    raised = _raised(updates)
    assert len(raised) == 1
    assert raised[0].camera_id == 1
    assert _resolved(updates) == []
    falls = [
        item.condition_id
        for item in snapshots[-1].conditions
        if item.reason is SafetyStateReason.FALL_DETECTED
    ]
    assert falls == ["fall_detected:fall:person"]
    _close(page, monitoring, pose)


def test_offline_camera_drops_its_fall_evidence(qtbot) -> None:
    page, monitoring, pose, updates, _ = _setup(qtbot)
    _hold(pose, {1: LYING}, 0.6)
    assert len(_raised(updates)) == 1

    pose.handle_camera_status(1, CameraStatus.OFFLINE)
    pose.handle_camera_status(1, CameraStatus.ONLINE)
    _hold(pose, {1: None}, 0.2)

    assert len(_resolved(updates)) == 1
    _close(page, monitoring, pose)


def test_fall_alert_payload_uses_the_fall_contract(qtbot) -> None:
    page, monitoring, pose, updates, _ = _setup(qtbot)
    _hold(pose, {1: LYING}, 0.6)
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(
            201,
            json={
                "event_id": body["event_id"],
                "alert_id": 3,
                "occurrence_id": 3,
                "duplicate": False,
            },
        )

    OperatorApiClient(
        base_url="https://api.example.test/v1",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=2.0,
        transport=httpx.MockTransport(handler),
    ).send_alert(_raised(updates)[0], "token")

    assert sent[0]["violation_type"] == "fall_detected"
    assert sent[0]["severity"] == "critical"
    assert sent[0]["camera_id"] == 1
    _close(page, monitoring, pose)
