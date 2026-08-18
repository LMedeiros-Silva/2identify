"""Continuous PPE monitoring controller for an active WorkSession."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import cast

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.controllers.active_camera_controller import ActiveCameraController
from app.core.config import AppSettings
from app.domain import (
    SafetyAlertSeverity,
    SafetyViolation,
    SafetyViolationType,
)
from app.engine import (
    AlertEngine,
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyEngine,
    PpeStabilityEngine,
)
from app.ui.active import ActiveOperationPage
from app.vision.ppe import (
    PpeDetectionBatch,
    PpeDetectionTracker,
    UltralyticsPpeDetector,
)
from app.vision.types import Frame
from app.workers.ppe_inference_worker import PpeInferenceWorker

logger = logging.getLogger(__name__)

ActivePpeWorkerFactory = Callable[[], PpeInferenceWorker]


class ActivePpeMonitoringController(QObject):
    """Run a fresh temporal PPE window throughout the active operation."""

    local_alert_update_ready = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        page: ActiveOperationPage,
        camera_controller: ActiveCameraController,
        worker_factory: ActivePpeWorkerFactory | None = None,
    ) -> None:
        super().__init__(page)
        self._page = page
        self._worker_factory = worker_factory or partial(
            PpeInferenceWorker,
            detector_factory=partial(
                UltralyticsPpeDetector,
                model_path=settings.ppe_model_path,
                expected_sha256=settings.ppe_model_sha256,
                confidence_threshold=settings.ppe_confidence_threshold,
                iou_threshold=settings.ppe_iou_threshold,
                image_size=settings.ppe_inference_image_size,
                device=settings.ppe_inference_device,
                config_directory=settings.ultralytics_config_directory,
            ),
        )
        self._stability_engine = PpeStabilityEngine(
            window_size=settings.ppe_stability_window_frames,
            minimum_samples=settings.ppe_stability_minimum_frames,
            present_ratio=settings.ppe_stability_present_ratio,
            absent_ratio=settings.ppe_stability_absent_ratio,
        )
        self._safety_engine = PpeSafetyEngine()
        self._alert_engine = AlertEngine(
            minimum_consecutive_observations=(
                settings.alert_minimum_consecutive_observations
            ),
            minimum_persistence_seconds=(
                settings.alert_minimum_persistence_seconds
            ),
            resolution_consecutive_observations=(
                settings.alert_resolution_consecutive_observations
            ),
            cooldown_seconds=settings.alert_cooldown_seconds,
        )
        self._tracker = PpeDetectionTracker(
            iou_threshold=settings.ppe_tracking_iou_threshold,
            maximum_missed_batches=settings.ppe_tracking_maximum_missed_batches,
            minimum_confirmation_hits=(
                settings.ppe_tracking_minimum_confirmation_hits
            ),
        )
        self._model_classes: frozenset[str] = frozenset()
        self._model_ready = False
        self._worker: PpeInferenceWorker | None = None
        self._restart_after_finish = False
        page.configure_detection_overlay(
            round(settings.ppe_release_assessment_max_age_seconds * 1_000)
        )
        camera_controller.analysis_frame_ready.connect(self.submit_frame)
        page.monitoring_start_requested.connect(self.start)
        page.monitoring_stop_requested.connect(self.stop)

    @property
    def is_running(self) -> bool:
        worker = self._worker
        return worker is not None and worker.isRunning()

    @Slot()
    def start(self) -> None:
        if not self._page.is_monitoring_active:
            return
        worker = self._worker
        if worker is not None and worker.isRunning():
            if worker.isInterruptionRequested():
                self._restart_after_finish = True
            return
        self._dispose_finished_worker()
        self._restart_after_finish = False
        self._reset_runtime()
        self._page.show_monitoring_inference_loading()
        worker = self._worker_factory()
        worker.model_ready.connect(self._handle_model_ready)
        worker.detections_ready.connect(self._handle_detections)
        worker.inference_failed.connect(self._handle_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("active_ppe_monitoring_started")
        worker.start()

    @Slot(object)
    def submit_frame(self, value: object) -> None:
        worker = self._worker
        if worker is None or not worker.isRunning() or not hasattr(value, "shape"):
            return
        worker.submit_frame(cast(Frame, value))

    @Slot()
    def stop(self) -> None:
        self._restart_after_finish = False
        self._reset_runtime()
        self._alert_engine.reset()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()

    def shutdown(self, wait_timeout_ms: int = 10_000) -> None:
        self._restart_after_finish = False
        self._reset_runtime()
        self._alert_engine.reset()
        worker = self._worker
        if worker is None:
            return
        worker.request_stop()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("active_ppe_monitoring_shutdown_timeout")
            return
        self._dispose_finished_worker()

    @Slot(object)
    def _handle_model_ready(self, value: object) -> None:
        operation = self._page.operation
        if (
            operation is None
            or not isinstance(value, tuple)
            or not all(isinstance(item, str) for item in value)
        ):
            self._handle_failure("O modelo retornou classes inválidas.", True)
            return
        model_classes = frozenset(item.strip().casefold() for item in value)
        required_classes = tuple(
            requirement.detection_class
            for requirement in operation.required_ppe
            if requirement.detection_class is not None
            and requirement.detection_class in model_classes
        )
        self._stability_engine.reset(required_classes)
        self._model_classes = model_classes
        self._model_ready = True
        self._page.show_monitoring_inference_ready(value)

    @Slot(object)
    def _handle_detections(self, value: object) -> None:
        operation = self._page.operation
        work_session = self._page.work_session
        if (
            not self._model_ready
            or operation is None
            or work_session is None
            or not isinstance(value, PpeDetectionBatch)
        ):
            return
        tracking_batch = self._tracker.update(value)
        self._page.update_monitoring_tracking_overlay(tracking_batch)
        snapshot = self._stability_engine.observe(value.observed_classes)
        assessment = self._safety_engine.evaluate(
            operation,
            self._model_classes,
            snapshot,
        )
        self._page.update_monitoring_assessment(assessment)
        alert_update = self._alert_engine.observe(
            work_session,
            self._violations_for(assessment),
            datetime.now(UTC),
        )
        if alert_update.raised_alerts or alert_update.resolved_alerts:
            self._page.update_local_alerts(alert_update)
            self.local_alert_update_ready.emit(alert_update)
            for alert in alert_update.raised_alerts:
                logger.warning(
                    "local_safety_alert_raised",
                    extra={
                        "alert_id": str(alert.alert_id),
                        "work_session_id": str(alert.work_session_id),
                        "violation_type": alert.violation.violation_type.value,
                    },
                )
            for alert in alert_update.resolved_alerts:
                logger.info(
                    "local_safety_alert_resolved",
                    extra={
                        "alert_id": str(alert.alert_id),
                        "work_session_id": str(alert.work_session_id),
                    },
                )

    @Slot(str, bool)
    def _handle_failure(self, message: str, unavailable: bool) -> None:
        self._reset_runtime()
        self._page.show_monitoring_inference_failure(message, unavailable)

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("active_ppe_monitoring_finished")
        self._dispose_finished_worker()
        if self._restart_after_finish and self._page.is_monitoring_active:
            self._restart_after_finish = False
            QTimer.singleShot(0, self.start)

    def _reset_runtime(self) -> None:
        self._model_ready = False
        self._model_classes = frozenset()
        self._stability_engine.reset()
        self._tracker.reset()

    @staticmethod
    def _violations_for(
        assessment: PpeSafetyAssessment,
    ) -> tuple[SafetyViolation, ...]:
        return tuple(
            SafetyViolation(
                violation_type=SafetyViolationType.PPE_ABSENT,
                subject_key=f"ppe:{requirement.ppe_id}",
                summary=f"EPI obrigatório ausente: {requirement.name}",
                severity=SafetyAlertSeverity.CRITICAL,
                ppe_id=requirement.ppe_id,
                ppe_name=requirement.name,
            )
            for requirement in assessment.requirements
            if requirement.state is PpeRequirementSafetyState.ABSENT
        )

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None
