from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel, QPushButton

from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import (
    NormalizedPoint,
    Operation,
    PpeRequirement,
    RiskAreaGeometry,
    RiskAreaReference,
    SafetyAlertSeverity,
    SafetyViolation,
    SafetyViolationType,
    WorkSession,
    WorkSessionStatus,
)
from app.engine import AlertEngine, PpeSafetyEngine, PpeStabilityEngine
from app.ui.active import ActiveOperationPage
from app.ui.components import CameraFrameView
from app.vision.ppe import (
    DetectionBox,
    PpeDetection,
    PpeDetectionBatch,
    PpeDetectionTracker,
)

_STARTED_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_SESSION_ID = UUID("11111111-1111-1111-1111-111111111111")


def _operator() -> OperatorSession:
    return OperatorSession(
        15,
        "João Silva",
        _STARTED_AT - timedelta(hours=1),
        AuthenticationMethod.FACE_ID,
    )


def _operation() -> Operation:
    return Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
        risk_area=RiskAreaReference(
            7,
            "Linha A",
            RiskAreaGeometry(
                (
                    NormalizedPoint(0.1, 0.6),
                    NormalizedPoint(0.4, 0.3),
                    NormalizedPoint(0.9, 0.8),
                )
            ),
            geometry_calibrated=True,
        ),
    )


def _work_session(*, operator_id: int = 15, operation_id: int = 41) -> WorkSession:
    return WorkSession(
        session_id=_SESSION_ID,
        operator_id=operator_id,
        operation_id=operation_id,
        camera_id=None,
        risk_area_id=7,
        verified_ppe_ids=(1,),
        safety_verified_at=_STARTED_AT - timedelta(milliseconds=100),
        ppe_sample_count=8,
        ppe_window_size=8,
        started_at=_STARTED_AT,
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
    )


def test_active_operation_page_presents_real_local_session(qtbot) -> None:
    page = ActiveOperationPage(
        _operator(),
        clock=lambda: _STARTED_AT + timedelta(hours=1, minutes=1, seconds=1),
    )
    qtbot.addWidget(page)

    page.set_work_session(_work_session(), _operation())

    assert page.is_active
    assert page.work_session.session_id == _SESSION_ID
    assert page.findChild(QLabel, "activeOperationName").text() == (
        "Inspeção de segurança"
    )
    assert page.findChild(QLabel, "activeDetailValue").text() == "João Silva"
    assert page.findChild(QLabel, "activeElapsed").text() == "01:01:01"
    assert page.findChild(QLabel, "activeSafetyValue").text() == "1 EPI confirmado"
    assert page.findChild(QLabel, "activeSessionCode").text() == str(
        _SESSION_ID
    ).upper()
    preview = page.findChild(CameraFrameView, "activeCameraPreview")
    assert preview.risk_zone_count == 1
    assert preview.risk_zone_labels == ("Linha A",)


def test_active_operation_page_emits_matching_finish_intent(qtbot) -> None:
    page = ActiveOperationPage(_operator(), clock=lambda: _STARTED_AT)
    qtbot.addWidget(page)
    page.set_work_session(_work_session(), _operation())
    finish_button = page.findChild(QPushButton, "activeFinishButton")

    with qtbot.waitSignal(page.finish_requested, timeout=1_000) as emitted:
        qtbot.mouseClick(finish_button, Qt.MouseButton.LeftButton)

    assert emitted.args == [str(_SESSION_ID)]
    assert not finish_button.isEnabled()
    assert finish_button.text() == "ENCERRANDO..."


def test_active_operation_page_rejects_mismatched_context() -> None:
    page = ActiveOperationPage(_operator())

    with pytest.raises(ValueError, match="operador autenticado"):
        page.set_work_session(_work_session(operator_id=22), _operation())
    with pytest.raises(ValueError, match="operação informada"):
        page.set_work_session(_work_session(operation_id=42), _operation())


def test_active_operation_page_does_not_overlay_uncalibrated_demo_zone(qtbot) -> None:
    page = ActiveOperationPage(_operator(), clock=lambda: _STARTED_AT)
    qtbot.addWidget(page)
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
        risk_area=RiskAreaReference(
            7,
            "Linha A",
            RiskAreaGeometry(
                (
                    NormalizedPoint(0.1, 0.6),
                    NormalizedPoint(0.4, 0.3),
                    NormalizedPoint(0.9, 0.8),
                )
            ),
        ),
    )

    page.set_work_session(_work_session(), operation)

    preview = page.findChild(CameraFrameView, "activeCameraPreview")
    assert preview.risk_zone_count == 0


def test_active_operation_page_presents_continuous_ppe_monitoring(qtbot) -> None:
    page = ActiveOperationPage(_operator(), clock=lambda: _STARTED_AT)
    qtbot.addWidget(page)
    operation = _operation()
    page.set_work_session(_work_session(), operation)

    with qtbot.waitSignal(page.monitoring_start_requested, timeout=1_000):
        page.activate_monitoring()

    page.update_monitoring_frame(QImage(160, 120, QImage.Format.Format_RGB888))
    page.show_monitoring_inference_ready(("capacete",))
    tracker = PpeDetectionTracker(
        iou_threshold=0.3,
        maximum_missed_batches=2,
        minimum_confirmation_hits=1,
    )
    page.update_monitoring_tracking_overlay(
        tracker.update(
            PpeDetectionBatch(
            detections=(
                PpeDetection(
                    0,
                    "capacete",
                    0.93,
                    DetectionBox(10, 15, 80, 105),
                ),
            ),
            frame_width=160,
            frame_height=120,
            inference_milliseconds=12.5,
            )
        )
    )
    stability = PpeStabilityEngine(
        window_size=5,
        minimum_samples=5,
        present_ratio=0.75,
        absent_ratio=0.25,
    )
    stability.reset(("capacete",))
    snapshot = stability.observe(("capacete",))
    for _ in range(4):
        snapshot = stability.observe(("capacete",))
    page.update_monitoring_assessment(
        PpeSafetyEngine().evaluate(operation, ("capacete",), snapshot)
    )

    preview = page.findChild(CameraFrameView, "activeCameraPreview")
    assert page.is_monitoring_active
    assert preview.has_frame
    assert preview.overlay_box_count == 1
    assert preview.overlay_labels == ("#1 capacete",)
    assert page.findChild(QLabel, "activeCameraStatus").text() == "ATIVA"
    assert page.findChild(QLabel, "activePpeState").text() == "CONFIRMADO"
    assert page.findChild(QLabel, "activeMonitoringStatus").text() == (
        "EPIs CONFORMES NO MONITORAMENTO ATUAL"
    )

    with qtbot.waitSignal(page.monitoring_stop_requested, timeout=1_000):
        page.deactivate_monitoring()

    assert not page.is_monitoring_active
    assert not preview.has_frame
    assert page.findChild(QLabel, "activeMonitoringStatus").text() == (
        "MONITORAMENTO NÃO INICIADO"
    )


def test_active_operation_page_exposes_camera_failure_and_retry(qtbot) -> None:
    page = ActiveOperationPage(_operator(), clock=lambda: _STARTED_AT)
    qtbot.addWidget(page)
    page.show()
    page.set_work_session(_work_session(), _operation())
    page.activate_monitoring()

    page.show_monitoring_camera_failure("Câmera ocupada.", True)

    assert page.findChild(QLabel, "activeCameraStatus").text() == "INDISPONÍVEL"
    assert page.findChild(QLabel, "activeMonitoringStatus").text() == (
        "MONITORAMENTO DE EPIs INTERROMPIDO"
    )
    retry = page.findChild(QPushButton, "activeCameraRetryButton")
    assert retry.isVisibleTo(page)
    with qtbot.waitSignal(page.monitoring_start_requested, timeout=1_000):
        qtbot.mouseClick(retry, Qt.MouseButton.LeftButton)

    assert page.findChild(QLabel, "activeCameraStatus").text() == "REINICIANDO"


def test_active_operation_page_presents_local_alert_lifecycle(qtbot) -> None:
    page = ActiveOperationPage(_operator(), clock=lambda: _STARTED_AT)
    qtbot.addWidget(page)
    session = _work_session()
    page.set_work_session(session, _operation())
    page.activate_monitoring()
    engine = AlertEngine(
        minimum_consecutive_observations=1,
        minimum_persistence_seconds=0,
        resolution_consecutive_observations=1,
        cooldown_seconds=30,
    )
    violation = SafetyViolation(
        SafetyViolationType.PPE_ABSENT,
        "ppe:1",
        "EPI obrigatório ausente: Capacete",
        SafetyAlertSeverity.CRITICAL,
        ppe_id=1,
        ppe_name="Capacete",
    )

    raised = engine.observe(session, (violation,), _STARTED_AT)
    page.update_local_alerts(raised)

    assert page.active_alert_count == 1
    assert page.findChild(QLabel, "activeAlertBadge").text() == (
        "1 ALERTA LOCAL ATIVO"
    )
    assert "NÃO SINCRONIZADO" in page.findChild(
        QLabel,
        "activeAlertMessage",
    ).text()

    resolved = engine.observe(session, (), _STARTED_AT + timedelta(seconds=1))
    page.update_local_alerts(resolved)

    assert page.active_alert_count == 0
    assert "Condição normalizada" in page.findChild(
        QLabel,
        "activeAlertMessage",
    ).text()
    page.deactivate_monitoring()
    assert page.findChild(QLabel, "activeAlertMessage").text() == (
        "Nenhuma ocorrência local · SEM ENVIO À API"
    )
