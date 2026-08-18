"""Lifecycle controller for per-frame PPE model observations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from time import monotonic
from typing import cast

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.controllers.safety_camera_controller import SafetyCameraController
from app.core.config import AppSettings
from app.domain import OperationStartAuthorization
from app.engine import PpeSafetyAssessment, PpeSafetyEngine, PpeStabilityEngine
from app.ui.safety import SafetyCameraState, SafetyVerificationPage
from app.vision.ppe import PpeDetectionBatch, UltralyticsPpeDetector
from app.vision.types import Frame
from app.workers.ppe_inference_worker import PpeInferenceWorker

logger = logging.getLogger(__name__)

PpeInferenceWorkerFactory = Callable[[], PpeInferenceWorker]


class PpeInferenceController(QObject):
    """Coordinate YOLO independently from camera capture and UI rendering."""

    operation_start_authorized = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        page: SafetyVerificationPage,
        camera_controller: SafetyCameraController,
        worker_factory: PpeInferenceWorkerFactory | None = None,
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
        self._assessment_max_age_seconds = (
            settings.ppe_release_assessment_max_age_seconds
        )
        self._model_classes: frozenset[str] = frozenset()
        self._latest_assessment: PpeSafetyAssessment | None = None
        self._latest_assessment_at: float | None = None
        self._start_authorized = False
        self._assessment_expiry_timer = QTimer(self)
        self._assessment_expiry_timer.setSingleShot(True)
        self._assessment_expiry_timer.setInterval(
            round(self._assessment_max_age_seconds * 1_000)
        )
        self._assessment_expiry_timer.timeout.connect(self._expire_assessment)
        page.configure_detection_overlay(
            round(self._assessment_max_age_seconds * 1_000)
        )
        self._model_ready = False
        self._worker: PpeInferenceWorker | None = None
        camera_controller.analysis_frame_ready.connect(self.submit_frame)
        page.camera_start_requested.connect(self.start)
        page.camera_stop_requested.connect(self.stop)
        page.operation_start_requested.connect(self._handle_operation_start_requested)

    @property
    def is_running(self) -> bool:
        worker = self._worker
        return worker is not None and worker.isRunning()

    @Slot()
    def start(self) -> None:
        """Load the model once per active verification route."""

        worker = self._worker
        if worker is not None and worker.isRunning():
            return

        self._dispose_finished_worker()
        self._model_ready = False
        self._model_classes = frozenset()
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._start_authorized = False
        self._assessment_expiry_timer.stop()
        self._stability_engine.reset()
        self._page.show_inference_loading()
        worker = self._worker_factory()
        worker.model_ready.connect(self._handle_model_ready)
        worker.detections_ready.connect(self._handle_detections)
        worker.inference_failed.connect(self._handle_inference_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("ppe_inference_attempt_started")
        worker.start()

    @Slot(object)
    def submit_frame(self, value: object) -> None:
        """Forward the latest owned camera frame through a non-queuing boundary."""

        worker = self._worker
        if worker is None or not worker.isRunning() or not hasattr(value, "shape"):
            return
        worker.submit_frame(cast(Frame, value))

    @Slot()
    def stop(self) -> None:
        self._model_ready = False
        self._model_classes = frozenset()
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._start_authorized = False
        self._assessment_expiry_timer.stop()
        self._stability_engine.reset()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()

    def shutdown(self, wait_timeout_ms: int = 10_000) -> None:
        self._model_ready = False
        self._model_classes = frozenset()
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._start_authorized = False
        self._assessment_expiry_timer.stop()
        self._stability_engine.reset()
        worker = self._worker
        if worker is None:
            return
        worker.request_stop()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("ppe_inference_worker_shutdown_timeout")
            return
        self._dispose_finished_worker()

    @Slot(object)
    def _handle_model_ready(self, value: object) -> None:
        if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
            model_classes = frozenset(item.strip().casefold() for item in value)
            operation = self._page.operation
            required_classes = (
                tuple(
                    requirement.detection_class
                    for requirement in operation.required_ppe
                    if requirement.detection_class is not None
                    and requirement.detection_class in model_classes
                )
                if operation is not None
                else ()
            )
            self._stability_engine.reset(required_classes)
            self._model_classes = model_classes
            self._latest_assessment = None
            self._latest_assessment_at = None
            self._start_authorized = False
            self._assessment_expiry_timer.stop()
            self._model_ready = True
            self._page.show_inference_ready(value)
            return
        self._handle_inference_failure(
            "O modelo de EPIs retornou classes inválidas.",
            True,
        )

    @Slot(object)
    def _handle_detections(self, value: object) -> None:
        if (
            self._model_ready
            and not self._start_authorized
            and isinstance(value, PpeDetectionBatch)
        ):
            operation = self._page.operation
            if operation is None:
                return
            self._page.update_ppe_detection_overlay(value)
            snapshot = self._stability_engine.observe(value.observed_classes)
            assessment = self._safety_engine.evaluate(
                operation,
                self._model_classes,
                snapshot,
            )
            self._latest_assessment = assessment
            self._latest_assessment_at = monotonic()
            if assessment.can_start_operation:
                self._assessment_expiry_timer.start()
            else:
                self._assessment_expiry_timer.stop()
            self._page.update_ppe_safety(assessment)

    @Slot(int)
    def _handle_operation_start_requested(self, operation_id: int) -> None:
        operation = self._page.operation
        assessment = self._latest_assessment
        assessment_at = self._latest_assessment_at
        if (
            not self._model_ready
            or self._start_authorized
            or operation is None
            or self._page.camera_state is not SafetyCameraState.ACTIVE
            or operation.operation_id != operation_id
            or assessment is None
            or assessment.operation_id != operation_id
            or not assessment.can_start_operation
            or assessment_at is None
            or monotonic() - assessment_at > self._assessment_max_age_seconds
        ):
            logger.warning(
                "operation_start_blocked_by_ppe_gate",
                extra={"operation_id": operation_id},
            )
            self._page.show_operation_start_rejected()
            return
        self._start_authorized = True
        authorization = OperationStartAuthorization(
            operation_id=operation_id,
            verified_ppe_ids=tuple(
                item.ppe_id for item in assessment.requirements
            ),
            sample_count=assessment.sample_count,
            window_size=assessment.window_size,
            authorized_at=datetime.now(UTC),
        )
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._assessment_expiry_timer.stop()
        logger.info(
            "operation_start_authorized_by_ppe_gate",
            extra={"operation_id": operation_id},
        )
        self._page.show_operation_start_authorized()
        self.operation_start_authorized.emit(authorization)

    @Slot()
    def _expire_assessment(self) -> None:
        assessment = self._latest_assessment
        if assessment is None or not assessment.can_start_operation:
            return
        self._latest_assessment = None
        self._latest_assessment_at = None
        logger.warning(
            "ppe_release_assessment_expired",
            extra={"operation_id": assessment.operation_id},
        )
        self._page.show_operation_start_rejected()

    @Slot(str, bool)
    def _handle_inference_failure(self, message: str, unavailable: bool) -> None:
        self._model_ready = False
        self._model_classes = frozenset()
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._start_authorized = False
        self._assessment_expiry_timer.stop()
        self._stability_engine.reset()
        self._page.show_inference_failure(message, unavailable)

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("ppe_inference_attempt_finished")
        self._dispose_finished_worker()

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None
