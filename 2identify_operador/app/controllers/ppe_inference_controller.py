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
from app.engine import (
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyEngine,
    PpeSafetyStatus,
    PpeStabilityEngine,
    PpeStabilitySnapshot,
)
from app.engine.helmet_placement import (
    HelmetPendingReason,
    HelmetPlacement,
    HelmetPlacementEngine,
    HelmetPlacementResult,
)
from app.engine.verification_subject import (
    SubjectIssue,
    VerificationSubject,
    identify_subject,
    subject_detections,
)
from app.ui.safety import SafetyCameraState, SafetyVerificationPage
from app.vision.pose import PoseDetectionBatch, UltralyticsPoseEstimator
from app.vision.ppe import PpeDetectionBatch, UltralyticsPpeDetector
from app.vision.types import Frame
from app.workers.pose_inference_worker import PoseInferenceWorker
from app.workers.ppe_inference_worker import PpeInferenceWorker

logger = logging.getLogger(__name__)

PpeInferenceWorkerFactory = Callable[[], PpeInferenceWorker]
PoseInferenceWorkerFactory = Callable[[], PoseInferenceWorker]

_HELMET_REASON_TEXT = {
    HelmetPendingReason.SEM_REFERENCIA: "rosto e ombros precisam aparecer na câmera",
    HelmetPendingReason.SEM_CAPACETE: "capacete não detectado no quadro atual",
    HelmetPendingReason.FORA_DA_CABECA: "capacete detectado fora da cabeça",
    HelmetPendingReason.ESTABILIZANDO: "confirmando o capacete na cabeça",
    HelmetPendingReason.OUTRA_PESSOA: "outra pessoa no quadro sem capacete confirmado",
}
_GATE_LOG_INTERVAL_SECONDS = 1.0


class PpeInferenceController(QObject):
    """Coordinate YOLO independently from camera capture and UI rendering."""

    operation_start_authorized = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        page: SafetyVerificationPage,
        camera_controller: SafetyCameraController,
        worker_factory: PpeInferenceWorkerFactory | None = None,
        pose_worker_factory: PoseInferenceWorkerFactory | None = None,
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
        self._pose_enabled = settings.pose_estimation_enabled
        self._pose_worker_factory = pose_worker_factory or partial(
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
        self._pose_worker: PoseInferenceWorker | None = None
        self._latest_pose: tuple[PoseDetectionBatch, float] | None = None
        # Same window and ratio as every other PPE, so one frame without evidence
        # (UNKNOWN) never erases the helmet-on-head observations already collected.
        self._helmet_engine = HelmetPlacementEngine(
            stability_frames=settings.ppe_stability_minimum_frames,
            window_frames=settings.ppe_stability_window_frames,
            present_ratio=settings.ppe_stability_present_ratio,
            maximum_missed_frames=settings.ppe_tracking_maximum_missed_batches,
        )
        self._stability_engine = PpeStabilityEngine(
            window_size=settings.ppe_stability_window_frames,
            minimum_samples=settings.ppe_stability_minimum_frames,
            present_ratio=settings.ppe_stability_present_ratio,
            absent_ratio=settings.ppe_stability_absent_ratio,
        )
        self._safety_engine = PpeSafetyEngine()
        self._minimum_samples = settings.ppe_stability_minimum_frames
        self._present_ratio = settings.ppe_stability_present_ratio
        self._last_gate_log: tuple[float, PpeSafetyStatus] | None = None
        self._assessment_max_age_seconds = settings.ppe_release_assessment_max_age_seconds
        self._model_classes: frozenset[str] = frozenset()
        self._required_classes: tuple[str, ...] = ()
        self._latest_assessment: PpeSafetyAssessment | None = None
        self._latest_assessment_at: float | None = None
        self._start_authorized = False
        self._auto_start_enabled = settings.ppe_auto_start_enabled
        self._auto_start_suspended = False
        self._restart_pending = False
        self._assessment_expiry_timer = QTimer(self)
        self._assessment_expiry_timer.setSingleShot(True)
        self._assessment_expiry_timer.setInterval(round(self._assessment_max_age_seconds * 1_000))
        self._assessment_expiry_timer.timeout.connect(self._expire_assessment)
        page.configure_detection_overlay(round(self._assessment_max_age_seconds * 1_000))
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
        if worker is not None and worker.isRunning() and not worker.isInterruptionRequested():
            return
        pose_worker = self._pose_worker
        if pose_worker is not None and pose_worker.isRunning():
            pose_worker.request_stop()
        if any(item is not None and item.isRunning() for item in (worker, pose_worker)):
            # The previous verification is still finishing its last inference. Start
            # again once it ends instead of dropping the request: the page would stay
            # without a model, and without any message, for the rest of the visit.
            self._restart_pending = True
            logger.info("safety_inference_start_deferred_until_previous_stops")
            return

        self._restart_pending = False
        self._dispose_finished_worker()
        self._dispose_finished_pose_worker()
        self._model_ready = False
        self._model_classes = frozenset()
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._start_authorized = False
        self._auto_start_suspended = False
        self._assessment_expiry_timer.stop()
        self._stability_engine.reset()
        self._helmet_engine.reset()
        self._latest_pose = None
        self._page.show_inference_loading()
        worker = self._worker_factory()
        worker.model_ready.connect(self._handle_model_ready)
        worker.detections_ready.connect(self._handle_detections)
        worker.inference_failed.connect(self._handle_inference_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("ppe_inference_attempt_started")
        worker.start()
        operation = self._page.operation
        # Pose identifies the single person being released, whatever PPE is required.
        if self._pose_enabled and operation is not None and operation.required_ppe:
            pose_worker = self._pose_worker_factory()
            pose_worker.poses_ready.connect(self._handle_poses)
            pose_worker.inference_failed.connect(self._handle_pose_failure)
            pose_worker.finished.connect(self._handle_pose_finished)
            self._pose_worker = pose_worker
            pose_worker.start()

    @Slot(object)
    def submit_frame(self, value: object) -> None:
        """Forward the latest owned camera frame through a non-queuing boundary."""

        if not hasattr(value, "shape"):
            return
        frame = cast(Frame, value)
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.submit_frame(frame)
        pose_worker = self._pose_worker
        if pose_worker is not None and pose_worker.isRunning():
            pose_worker.submit_frame(frame)

    @Slot(object)
    def _handle_poses(self, value: object) -> None:
        sender = self.sender()
        if sender is not None and sender is not self._pose_worker:
            return
        if isinstance(value, PoseDetectionBatch):
            self._latest_pose = value, monotonic()

    @Slot(str, bool)
    def _handle_pose_failure(self, message: str, unavailable: bool) -> None:
        logger.warning(
            "helmet_pose_unavailable", extra={"reason": message, "unavailable": unavailable}
        )
        self._latest_pose = None
        self._helmet_engine.reset()

    def _recent_pose(self) -> PoseDetectionBatch | None:
        entry = self._latest_pose
        if entry is None or monotonic() - entry[1] > 1.0:
            return None
        return entry[0]

    @Slot()
    def stop(self) -> None:
        self._restart_pending = False
        self._model_ready = False
        self._model_classes = frozenset()
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._start_authorized = False
        self._assessment_expiry_timer.stop()
        self._stability_engine.reset()
        self._helmet_engine.reset()
        self._latest_pose = None
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
        pose_worker = self._pose_worker
        if pose_worker is not None and pose_worker.isRunning():
            pose_worker.request_stop()

    def shutdown(self, wait_timeout_ms: int = 10_000) -> bool:
        self._restart_pending = False
        self._model_ready = False
        self._model_classes = frozenset()
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._start_authorized = False
        self._assessment_expiry_timer.stop()
        self._stability_engine.reset()
        self._helmet_engine.reset()
        self._latest_pose = None
        worker = self._worker
        pose_worker = self._pose_worker
        for active_worker in (worker, pose_worker):
            if active_worker is not None:
                active_worker.request_stop()
        for active_worker in (worker, pose_worker):
            if (
                active_worker is not None
                and active_worker.isRunning()
                and not active_worker.wait(wait_timeout_ms)
            ):
                logger.error("safety_inference_worker_shutdown_timeout")
                return False
        self._dispose_finished_worker()
        self._dispose_finished_pose_worker()
        return True

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
            self._required_classes = required_classes
            self._model_classes = model_classes
            self._latest_assessment = None
            self._latest_assessment_at = None
            self._start_authorized = False
            self._auto_start_suspended = False
            self._assessment_expiry_timer.stop()
            self._model_ready = True
            self._last_gate_log = None
            self._log_requirement_mapping(model_classes)
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
            pose = self._recent_pose()
            subject = identify_subject(value, pose)
            evidence = subject_detections(value, subject)
            if subject.identified:
                snapshot = self._stability_engine.observe(evidence.observed_classes)
                helmet = self._helmet_engine.observe(evidence, pose)
            else:
                # Evidence from nobody, from several people or from an unreliable skeleton
                # is discarded: the window restarts with the one person being released.
                self._stability_engine.reset(self._required_classes)
                self._helmet_engine.reset()
                snapshot = self._stability_engine.observe(())
                # The empty frame only produces a COLLECTING snapshot; it is not kept.
                self._stability_engine.reset(self._required_classes)
                helmet = self._helmet_engine.observe(evidence, None)
            assessment = self._safety_engine.evaluate(
                operation,
                self._model_classes,
                snapshot,
                helmet_placement=helmet.overall,
            )
            self._latest_assessment = assessment
            self._latest_assessment_at = monotonic()
            if assessment.can_start_operation:
                self._assessment_expiry_timer.start()
            else:
                self._assessment_expiry_timer.stop()
            self._page.update_ppe_safety(assessment)
            reasons = (
                self._pending_reasons(assessment, snapshot, helmet)
                if subject.identified
                else (f"Pessoa: {self._subject_reason(subject)}",)
            )
            if assessment.status is PpeSafetyStatus.PENDING:
                self._page.show_pending_reasons(reasons)
            self._log_gate(assessment, snapshot, helmet, value, subject)
            if (
                assessment.can_start_operation
                and self._auto_start_enabled
                and not self._auto_start_suspended
            ):
                self._authorize_start(operation.operation_id, automatic=True)

    def _subject_reason(self, subject: VerificationSubject) -> str:
        if subject.issue is SubjectIssue.VARIAS_PESSOAS:
            return f"{subject.people} pessoas na câmera, a verificação exige apenas o operador"
        if subject.issue is SubjectIssue.NENHUMA_PESSOA:
            return "nenhuma pessoa identificada na câmera"
        if subject.issue is SubjectIssue.PESSOA_INCERTA:
            return "sem referência confiável da pessoa (rosto e ombros visíveis)"
        if not self._pose_enabled:
            return (
                "estimativa de postura desativada, não é possível confirmar que há uma "
                "única pessoa"
            )
        if self._pose_worker is not None and self._pose_worker.isRunning():
            return "aguardando a estimativa de postura para identificar a pessoa"
        return "estimativa de postura indisponível, não é possível confirmar uma única pessoa"

    def _pending_reasons(
        self,
        assessment: PpeSafetyAssessment,
        snapshot: PpeStabilitySnapshot,
        helmet: HelmetPlacementResult,
    ) -> tuple[str, ...]:
        """Per-requirement explanation built from the same evidence as the gate."""

        reasons = []
        for item in assessment.requirements:
            if item.state is PpeRequirementSafetyState.CONFIRMED:
                continue
            if item.state is PpeRequirementSafetyState.UNMAPPED:
                detail = (
                    f"o modelo não tem a classe '{item.detection_class}'"
                    if item.detection_class is not None
                    else "sem classe correspondente no modelo"
                )
            elif item.state is PpeRequirementSafetyState.ABSENT:
                detail = (
                    "capacete na mão"
                    if helmet.overall is HelmetPlacement.NA_MAO
                    and item.detection_class == "capacete"
                    else "ausente"
                )
            elif item.detection_class == "capacete" and helmet.pending_reason is not None:
                if helmet.pending_reason is HelmetPendingReason.SEM_POSE:
                    detail = (
                        "aguardando a estimativa de postura"
                        if self._pose_worker is not None and self._pose_worker.isRunning()
                        else "estimativa de postura indisponível, o capacete não pode ser "
                        "confirmado na cabeça"
                    )
                else:
                    detail = _HELMET_REASON_TEXT[helmet.pending_reason]
            else:
                decision = (
                    snapshot.decision_for(item.detection_class)
                    if item.detection_class is not None
                    else None
                )
                if decision is None or snapshot.sample_count < self._minimum_samples:
                    detail = (
                        f"coletando amostras ({snapshot.sample_count}/{self._minimum_samples})"
                    )
                else:
                    detail = (
                        f"visto em {decision.observed_frames} de {decision.sample_count} "
                        f"quadros (mínimo {self._present_ratio:.0%})"
                    )
            reasons.append(f"{item.name}: {detail}")
        return tuple(reasons)

    def _log_requirement_mapping(self, model_classes: frozenset[str]) -> None:
        operation = self._page.operation
        if operation is None:
            return
        logger.info(
            "ppe_requirement_mapping",
            extra={
                "operation_id": operation.operation_id,
                "model_classes": sorted(model_classes),
                "requirements": [
                    {
                        "ppe_id": item.ppe_id,
                        "name": item.name,
                        "detection_class": item.detection_class,
                        "in_model": item.detection_class in model_classes,
                    }
                    for item in operation.required_ppe
                ],
            },
        )

    def _log_gate(
        self,
        assessment: PpeSafetyAssessment,
        snapshot: PpeStabilitySnapshot,
        helmet: HelmetPlacementResult,
        batch: PpeDetectionBatch,
        subject: VerificationSubject,
    ) -> None:
        # One line per second (or on a status change) explains a blocked release.
        now = monotonic()
        last = self._last_gate_log
        if (
            last is not None
            and last[1] is assessment.status
            and now - last[0] < _GATE_LOG_INTERVAL_SECONDS
        ):
            return
        self._last_gate_log = now, assessment.status
        logger.info(
            "ppe_gate_snapshot",
            extra={
                "operation_id": assessment.operation_id,
                "status": assessment.status.value,
                "samples": f"{snapshot.sample_count}/{snapshot.window_size}",
                "frame_detections": sorted(
                    f"{item.class_name}:{item.confidence:.2f}" for item in batch.detections
                ),
                "requirements": [
                    {
                        "name": item.name,
                        "detection_class": item.detection_class,
                        "state": item.state.value,
                        "observed": (
                            decision.observed_frames
                            if item.detection_class is not None
                            and (decision := snapshot.decision_for(item.detection_class))
                            else None
                        ),
                    }
                    for item in assessment.requirements
                ],
                "subject": subject.issue.value if subject.issue else "uma_pessoa",
                "people": subject.people,
                "helmet": helmet.overall.value,
                "helmet_reason": (
                    helmet.pending_reason.value if helmet.pending_reason is not None else None
                ),
                "pose_age_seconds": (
                    round(now - self._latest_pose[1], 2) if self._latest_pose else None
                ),
            },
        )

    @Slot(int)
    def _handle_operation_start_requested(self, operation_id: int) -> None:
        self._authorize_start(operation_id, automatic=False)

    def _authorize_start(self, operation_id: int, *, automatic: bool) -> None:
        """Single release gate for the button and the automatic start."""

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
                extra={"operation_id": operation_id, "automatic": automatic},
            )
            if not automatic:
                self._page.show_operation_start_rejected()
            return
        self._start_authorized = True
        authorization = OperationStartAuthorization(
            operation_id=operation_id,
            verified_ppe_ids=tuple(item.ppe_id for item in assessment.requirements),
            sample_count=assessment.sample_count,
            window_size=assessment.window_size,
            authorized_at=datetime.now(UTC),
        )
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._assessment_expiry_timer.stop()
        logger.info(
            "operation_start_authorized_by_ppe_gate",
            extra={"operation_id": operation_id, "automatic": automatic},
        )
        self._page.show_operation_start_authorized()
        self.operation_start_authorized.emit(authorization)

    @Slot()
    def handle_operation_start_rejected(self) -> None:
        """The WorkSession was not created: re-arm the gate with fresh evidence.

        Without this the one-shot flag stayed set and every later detection was ignored,
        leaving the page on "VERIFICAÇÃO EXPIRADA" for good. Automatic start stays
        suspended until the next verification so a persistent failure is not retried in
        a loop; the button is enabled again by the next compliant assessment.
        """

        self._start_authorized = False
        self._auto_start_suspended = True
        self._latest_assessment = None
        self._latest_assessment_at = None
        self._assessment_expiry_timer.stop()
        operation = self._page.operation
        self._stability_engine.reset(
            tuple(
                requirement.detection_class
                for requirement in operation.required_ppe
                if requirement.detection_class is not None
                and requirement.detection_class in self._model_classes
            )
            if operation is not None
            else ()
        )
        self._helmet_engine.reset()
        logger.warning("operation_start_rejected_after_ppe_authorization")

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
        self._helmet_engine.reset()
        self._latest_pose = None
        self._page.show_inference_failure(message, unavailable)

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("ppe_inference_attempt_finished")
        self._dispose_finished_worker()
        self._resume_pending_start()

    @Slot()
    def _handle_pose_finished(self) -> None:
        self._dispose_finished_pose_worker()
        self._resume_pending_start()

    def _resume_pending_start(self) -> None:
        if not self._restart_pending:
            return
        if any(item is not None and item.isRunning() for item in (self._worker, self._pose_worker)):
            return
        self._restart_pending = False
        self.start()

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None

    def _dispose_finished_pose_worker(self) -> None:
        worker = self._pose_worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._pose_worker = None
