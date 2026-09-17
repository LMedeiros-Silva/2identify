"""Continuous pose-estimation controller for an active WorkSession."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from typing import cast

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.controllers.active_camera_controller import ActiveCameraController
from app.core.config import AppSettings
from app.domain.camera_source import CameraFrame, CameraStatus
from app.engine import ErgonomicsEngine, RiskAreaPoseEngine
from app.ui.active import ActiveOperationPage
from app.vision.pose import PoseDetectionBatch, UltralyticsPoseEstimator
from app.vision.types import Frame
from app.workers.pose_inference_worker import PoseInferenceWorker

logger = logging.getLogger(__name__)

ActivePoseWorkerFactory = Callable[[], PoseInferenceWorker]


class ActiveErgonomicsMonitoringController(QObject):
    """Estimate pose from the operational camera and screen ergonomic risks."""

    assessment_ready = Signal(object)
    risk_area_assessment_ready = Signal(object)
    pose_batch_ready = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        page: ActiveOperationPage,
        camera_controller: ActiveCameraController,
        worker_factory: ActivePoseWorkerFactory | None = None,
    ) -> None:
        super().__init__(page)
        self._page = page
        self._camera_controller = camera_controller
        self._enabled = settings.pose_estimation_enabled
        self._pose_camera_ids = settings.parsed_pose_camera_ids
        self._worker_factory = worker_factory or partial(
            PoseInferenceWorker,
            estimator_factory=partial(
                UltralyticsPoseEstimator,
                model_path=settings.pose_model_path,
                expected_sha256=settings.pose_model_sha256,
                confidence_threshold=settings.pose_confidence_threshold,
                image_size=settings.pose_inference_image_size,
                device=settings.pose_inference_device,
                config_directory=settings.ultralytics_config_directory,
            ),
        )
        self._engine = ErgonomicsEngine(
            keypoint_confidence_threshold=(settings.pose_keypoint_confidence_threshold),
            trunk_warning_degrees=settings.ergonomics_trunk_warning_degrees,
            trunk_critical_degrees=settings.ergonomics_trunk_critical_degrees,
            overhead_reach_enabled=settings.ergonomics_overhead_reach_enabled,
            knee_flexion_enabled=settings.ergonomics_knee_flexion_enabled,
            knee_warning_degrees=settings.ergonomics_knee_warning_degrees,
            knee_critical_degrees=settings.ergonomics_knee_critical_degrees,
        )
        self._risk_area_engine = RiskAreaPoseEngine(
            keypoint_confidence_threshold=(
                settings.pose_keypoint_confidence_threshold
            ),
        )
        self._page.configure_pose_overlay(
            minimum_keypoint_confidence=(settings.pose_keypoint_confidence_threshold),
            maximum_age_ms=max(
                1_000,
                round(3_000 / settings.pose_inference_fps),
            ),
        )
        self._worker: PoseInferenceWorker | None = None
        self._model_ready = False
        self._restart_after_finish = False
        self._camera_statuses: dict[int, CameraStatus] = {}
        camera_controller.analysis_frame_ready.connect(self.submit_frame)
        camera_controller.status_changed.connect(self.handle_camera_status)
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
        if not self._enabled:
            self._page.show_ergonomics_disabled()
            return
        worker = self._worker
        if worker is not None and worker.isRunning():
            if worker.isInterruptionRequested():
                self._restart_after_finish = True
            return
        self._dispose_finished_worker()
        self._restart_after_finish = False
        self._model_ready = False
        self._camera_statuses.clear()
        self._page.show_ergonomics_loading()
        worker = self._worker_factory()
        worker.model_ready.connect(self._handle_model_ready)
        worker.poses_ready.connect(self._handle_poses)
        worker.inference_failed.connect(self._handle_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("active_ergonomics_monitoring_started")
        worker.start()

    @Slot(object)
    def submit_frame(self, value: object) -> None:
        worker = self._worker
        if not self._model_ready or worker is None or not worker.isRunning():
            return
        if isinstance(value, CameraFrame):
            if (
                value.generation == self._camera_controller.generation
                and (self._pose_camera_ids is None or value.camera_id in self._pose_camera_ids)
            ):
                worker.submit_frame(value)
        elif hasattr(value, "shape"):
            worker.submit_frame(cast(Frame, value))

    @Slot()
    def stop(self) -> None:
        self._restart_after_finish = False
        self._model_ready = False
        self._camera_statuses.clear()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()

    def shutdown(self, wait_timeout_ms: int = 10_000) -> None:
        self._restart_after_finish = False
        self._model_ready = False
        self._camera_statuses.clear()
        worker = self._worker
        if worker is None:
            return
        worker.request_stop()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("active_ergonomics_monitoring_shutdown_timeout")
            return
        self._dispose_finished_worker()

    @Slot()
    def _handle_model_ready(self) -> None:
        sender = self.sender()
        if sender is not None and sender is not self._worker:
            return
        self._model_ready = True
        self._page.show_ergonomics_ready()

    @Slot(object)
    def _handle_poses(self, value: object) -> None:
        sender = self.sender()
        if sender is not None and sender is not self._worker:
            return
        if not self._model_ready or not isinstance(value, PoseDetectionBatch):
            return
        if (
            value.camera_id is not None
            and (
                value.generation != self._camera_controller.generation
                or value.camera_id not in {item.camera_id for item in self._page.selected_cameras}
                or (
                    self._camera_statuses.get(value.camera_id) is not None
                    and self._camera_statuses[value.camera_id] is not CameraStatus.ONLINE
                )
                or (
                    value.captured_at is not None
                    and (datetime.now(UTC) - value.captured_at).total_seconds() > 2.0
                )
            )
        ):
            return
        self._page.update_monitoring_pose_overlay(value)
        self.pose_batch_ready.emit(value)
        assessment = self._engine.evaluate(value)
        if value.camera_id is not None:
            assessment = replace(
                assessment,
                camera_id=value.camera_id,
                captured_at=value.captured_at,
                violations=tuple(
                    replace(item, camera_id=value.camera_id)
                    for item in assessment.violations
                ),
            )
        self._page.update_ergonomic_assessment(assessment)
        self.assessment_ready.emit(assessment)
        operation = self._page.operation
        risk_area = operation.risk_area if operation is not None else None
        if (
            risk_area is None
            or risk_area.geometry is None
            or not risk_area.geometry_calibrated
        ):
            self._page.show_risk_area_monitoring_unavailable()
            return
        if value.camera_id is not None and value.camera_id != risk_area.camera_id:
            return
        risk_assessment = self._risk_area_engine.evaluate(
            value,
            risk_area.geometry,
            risk_area_id=risk_area.risk_area_id,
            risk_area_name=risk_area.name,
        )
        if value.camera_id is not None:
            risk_assessment = replace(
                risk_assessment,
                camera_id=value.camera_id,
                captured_at=value.captured_at,
                violations=tuple(
                    replace(
                        item,
                        camera_id=value.camera_id,
                        risk_area_id=risk_area.risk_area_id,
                    )
                    for item in risk_assessment.violations
                ),
            )
        self._page.update_risk_area_assessment(risk_assessment)
        self.risk_area_assessment_ready.emit(risk_assessment)

    @Slot(int, object)
    def handle_camera_status(self, camera_id: int, status: object) -> None:
        if isinstance(status, CameraStatus):
            self._camera_statuses[camera_id] = status

    @Slot(str, bool)
    def _handle_failure(self, message: str, unavailable: bool) -> None:
        sender = self.sender()
        if sender is not None and sender is not self._worker:
            return
        self._model_ready = False
        self._page.show_ergonomics_failure(message, unavailable)

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("active_ergonomics_monitoring_finished")
        self._dispose_finished_worker()
        if self._restart_after_finish and self._page.is_monitoring_active:
            self._restart_after_finish = False
            QTimer.singleShot(0, self.start)

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None
