"""Application-level authentication and window navigation controller."""

from __future__ import annotations

import logging
from functools import partial
from uuid import UUID

from PySide6.QtCore import QObject, Slot

from app.core.config import AppSettings
from app.core.session import (
    AuthenticationMethod,
    OperatorSession,
    OperatorSessionAlreadyActiveError,
    OperatorSessionContext,
)
from app.domain import OperationStartAuthorization, SafetyAlert
from app.domain.auth import CredentialAuthenticationResult, OperatorIdentity
from app.engine import AlertEngineUpdate
from app.services.alert_delivery_service import AlertDeliveryReceipt, AlertSender
from app.services.manual_service import ManualService
from app.services.operation_service import OperationService
from app.services.safety_state_service import (
    SafetyStateDeliveryError,
    SafetyStateDeliveryReceipt,
    SafetyStateSender,
    SafetyStateSnapshot,
)
from app.services.work_session_service import WorkSessionError, WorkSessionService
from app.ui.login import LoginWindow
from app.ui.main import MainWindow
from app.workers.alert_delivery_worker import AlertDeliveryWorker
from app.workers.safety_state_delivery_worker import SafetyStateDeliveryWorker

from .active_camera_controller import ActiveCameraController
from .active_ergonomics_monitoring_controller import (
    ActiveErgonomicsMonitoringController,
)
from .active_ppe_monitoring_controller import ActivePpeMonitoringController
from .operations_controller import OperationsController
from .ppe_inference_controller import PpeInferenceController
from .risk_area_snapshot_controller import RiskAreaSnapshotController
from .safety_camera_controller import SafetyCameraController

logger = logging.getLogger(__name__)


class ApplicationController(QObject):
    """Create the authenticated shell and enforce a single window transition."""

    def __init__(
        self,
        session_context: OperatorSessionContext,
        login_window: LoginWindow,
        app_version: str,
        operation_service: OperationService | None = None,
        operations_source_notice: str | None = None,
        manual_service: ManualService | None = None,
        settings: AppSettings | None = None,
        work_session_service: WorkSessionService | None = None,
        alert_sender: AlertSender | None = None,
        safety_state_sender: SafetyStateSender | None = None,
    ) -> None:
        super().__init__(login_window)
        self._session_context = session_context
        self._login_window = login_window
        self._app_version = app_version
        self._operation_service = operation_service
        self._operations_source_notice = operations_source_notice
        self._manual_service = manual_service
        self._settings = settings
        self._alert_sender = alert_sender
        self._safety_state_sender = safety_state_sender
        self._work_session_service = work_session_service or WorkSessionService(
            maximum_authorization_age_seconds=(
                settings.ppe_release_assessment_max_age_seconds if settings is not None else 2.0
            )
        )
        self._operations_controller: OperationsController | None = None
        self._risk_area_snapshot_controller: RiskAreaSnapshotController | None = None
        self._safety_camera_controller: SafetyCameraController | None = None
        self._ppe_inference_controller: PpeInferenceController | None = None
        self._active_camera_controller: ActiveCameraController | None = None
        self._active_ergonomics_monitoring_controller: (
            ActiveErgonomicsMonitoringController | None
        ) = None
        self._active_ppe_monitoring_controller: ActivePpeMonitoringController | None = None
        self._main_window: MainWindow | None = None
        self._alert_delivery_workers: dict[str, AlertDeliveryWorker] = {}
        self._pending_alert_deliveries: dict[str, SafetyAlert] = {}
        self._safety_state_delivery_worker: SafetyStateDeliveryWorker | None = None
        self._pending_safety_state_snapshot: SafetyStateSnapshot | None = None

    @property
    def main_window(self) -> MainWindow | None:
        return self._main_window

    @property
    def work_session_service(self) -> WorkSessionService:
        return self._work_session_service

    @Slot(object)
    def handle_face_authentication(self, result: object) -> None:
        if not isinstance(result, OperatorIdentity):
            logger.error("invalid_face_login_result_type")
            self._login_window.show_face_authentication_error(
                "Não foi possível criar a sessão do operador."
            )
            return

        self._open_session_and_main_window(
            operator_id=result.operator_id,
            operator_name=result.name,
            authentication_method=AuthenticationMethod.FACE_ID,
        )

    @Slot(object)
    def handle_credential_authentication(self, result: object) -> None:
        if not isinstance(result, CredentialAuthenticationResult):
            logger.error("invalid_credential_login_result_type")
            self._login_window.show_credential_authentication_error(
                "Não foi possível criar a sessão do operador."
            )
            return

        self._open_session_and_main_window(
            operator_id=result.operator_id,
            operator_name=result.name,
            authentication_method=AuthenticationMethod.CREDENTIALS,
            access_token=result.access_token,
        )

    def _open_session_and_main_window(
        self,
        operator_id: int,
        operator_name: str,
        authentication_method: AuthenticationMethod,
        access_token: str | None = None,
    ) -> None:
        try:
            session = self._session_context.open(
                operator_id=operator_id,
                operator_name=operator_name,
                authentication_method=authentication_method,
                access_token=access_token,
            )
        except OperatorSessionAlreadyActiveError:
            logger.warning("operator_window_transition_ignored_active_session")
            if self._main_window is not None:
                self._main_window.raise_()
                self._main_window.activateWindow()
            return

        try:
            self._show_main_window(session)
        except Exception:
            self._session_context.close()
            raise

    def _show_main_window(self, session: OperatorSession) -> None:
        main_window = MainWindow(session=session, app_version=self._app_version)
        main_window.logout_requested.connect(self.handle_logout)
        if self._settings is not None:
            self._safety_camera_controller = SafetyCameraController(
                settings=self._settings,
                page=main_window.safety_verification_page,
            )
            self._ppe_inference_controller = PpeInferenceController(
                settings=self._settings,
                page=main_window.safety_verification_page,
                camera_controller=self._safety_camera_controller,
            )
            self._ppe_inference_controller.operation_start_authorized.connect(
                self.handle_operation_start_authorized
            )
            self._active_camera_controller = ActiveCameraController(
                settings=self._settings,
                page=main_window.active_operation_page,
            )
            self._active_ppe_monitoring_controller = ActivePpeMonitoringController(
                settings=self._settings,
                page=main_window.active_operation_page,
                camera_controller=self._active_camera_controller,
            )
            self._active_ergonomics_monitoring_controller = ActiveErgonomicsMonitoringController(
                settings=self._settings,
                page=main_window.active_operation_page,
                camera_controller=self._active_camera_controller,
            )
            self._active_ergonomics_monitoring_controller.assessment_ready.connect(
                self._active_ppe_monitoring_controller.handle_ergonomic_assessment
            )
            self._active_ergonomics_monitoring_controller.risk_area_assessment_ready.connect(
                self._active_ppe_monitoring_controller.handle_risk_area_assessment
            )
            self._active_ppe_monitoring_controller.local_alert_update_ready.connect(
                self._handle_local_alert_update
            )
            self._active_ppe_monitoring_controller.safety_state_snapshot_ready.connect(
                self._handle_safety_state_snapshot
            )
        if self._operation_service is not None:
            self._operations_controller = OperationsController(
                service=self._operation_service,
                page=main_window.operations_page,
                source_notice=self._operations_source_notice,
                manual_service=self._manual_service,
            )
            self._operations_controller.safety_verification_requested.connect(
                main_window.show_safety_verification
            )
            if self._settings is not None:
                self._risk_area_snapshot_controller = RiskAreaSnapshotController(
                    settings=self._settings,
                    page=main_window.operations_page,
                )
                self._operations_controller.risk_area_requested.connect(
                    self._risk_area_snapshot_controller.capture
                )
            self._operations_controller.load_operations()
        main_window.active_operation_page.finish_requested.connect(
            self.handle_work_session_finish_requested
        )
        self._main_window = main_window
        main_window.showMaximized()
        self._login_window.hide()
        logger.info(
            "operator_main_window_opened",
            extra={
                "operator_id": session.operator_id,
                "authentication_method": session.authentication_method.value,
            },
        )

    @Slot()
    def handle_logout(self) -> None:
        """Close the authenticated context and restore a clean login window."""

        main_window = self._main_window
        if main_window is None:
            logger.warning("operator_logout_ignored_without_main_window")
            return

        session = self._session_context.require_current()
        self._shutdown_alert_delivery_workers()
        if self._risk_area_snapshot_controller is not None:
            self._risk_area_snapshot_controller.shutdown()
        if self._operations_controller is not None:
            self._operations_controller.shutdown()
        if self._active_ergonomics_monitoring_controller is not None:
            self._active_ergonomics_monitoring_controller.shutdown()
        if self._active_ppe_monitoring_controller is not None:
            self._active_ppe_monitoring_controller.shutdown()
        self._shutdown_safety_state_delivery_worker()
        if self._active_camera_controller is not None:
            self._active_camera_controller.shutdown()
        if self._ppe_inference_controller is not None:
            self._ppe_inference_controller.shutdown()
        if self._safety_camera_controller is not None:
            self._safety_camera_controller.shutdown()
        self._work_session_service.interrupt_active()
        self._login_window.reset_for_authentication()
        self._session_context.close()
        self._login_window.show()
        self._login_window.raise_()
        self._login_window.activateWindow()
        main_window.close()
        self._main_window = None
        self._operations_controller = None
        self._risk_area_snapshot_controller = None
        self._safety_camera_controller = None
        self._ppe_inference_controller = None
        self._active_camera_controller = None
        self._active_ergonomics_monitoring_controller = None
        self._active_ppe_monitoring_controller = None
        logger.info("operator_logout_complete", extra={"operator_id": session.operator_id})

    @Slot()
    def shutdown(self) -> None:
        """Stop authenticated camera resources during process teardown."""

        self._shutdown_alert_delivery_workers()
        if self._risk_area_snapshot_controller is not None:
            self._risk_area_snapshot_controller.shutdown()
        if self._operations_controller is not None:
            self._operations_controller.shutdown()
        if self._active_ergonomics_monitoring_controller is not None:
            self._active_ergonomics_monitoring_controller.shutdown()
        if self._active_ppe_monitoring_controller is not None:
            self._active_ppe_monitoring_controller.shutdown()
        self._shutdown_safety_state_delivery_worker()
        if self._active_camera_controller is not None:
            self._active_camera_controller.shutdown()
        if self._ppe_inference_controller is not None:
            self._ppe_inference_controller.shutdown()
        if self._safety_camera_controller is not None:
            self._safety_camera_controller.shutdown()
        self._work_session_service.interrupt_active()

    @Slot(object)
    def _handle_local_alert_update(self, value: object) -> None:
        if not isinstance(value, AlertEngineUpdate):
            return
        delivery_alerts = (*value.raised_alerts, *value.escalated_alerts)
        if not delivery_alerts:
            return
        main_window = self._main_window
        session = self._session_context.current
        settings = self._settings
        sender = self._alert_sender
        if main_window is None:
            return
        if session is None or session.access_token is None or sender is None or settings is None:
            for alert in delivery_alerts:
                main_window.active_operation_page.show_alert_delivery_failure(
                    str(alert.alert_id),
                    "Alerta local: entre com e-mail e senha para enviar ao Admin.",
                )
            return
        for alert in delivery_alerts:
            event_id = str(alert.alert_id)
            if event_id in self._alert_delivery_workers:
                if alert in value.escalated_alerts:
                    self._pending_alert_deliveries[event_id] = alert
                continue
            self._start_alert_delivery(alert, session.access_token)

    def _start_alert_delivery(
        self,
        alert: SafetyAlert,
        access_token: str,
    ) -> None:
        sender = self._alert_sender
        settings = self._settings
        if sender is None or settings is None:
            return
        worker = AlertDeliveryWorker(
            sender,
            alert,
            access_token,
            maximum_attempts=settings.alert_delivery_max_attempts,
            retry_delay_seconds=settings.alert_delivery_retry_delay_seconds,
        )
        worker.delivered.connect(self._handle_alert_delivered)
        worker.delivery_failed.connect(self._handle_alert_delivery_failed)
        worker.finished.connect(partial(self._dispose_alert_delivery_worker, worker))
        self._alert_delivery_workers[worker.event_id] = worker
        worker.start()

    @Slot(object)
    def _handle_alert_delivered(self, value: object) -> None:
        if not isinstance(value, AlertDeliveryReceipt) or self._main_window is None:
            return
        self._main_window.active_operation_page.show_alert_delivery_succeeded(
            str(value.event_id),
            value.alert_id,
        )

    @Slot(str, str)
    def _handle_alert_delivery_failed(self, event_id: str, message: str) -> None:
        if self._main_window is not None:
            self._main_window.active_operation_page.show_alert_delivery_failure(
                event_id,
                message,
            )

    @Slot(object)
    def _handle_safety_state_snapshot(self, value: object) -> None:
        if not isinstance(value, SafetyStateSnapshot):
            return
        session = self._session_context.current
        settings = self._settings
        sender = self._safety_state_sender
        if (
            session is None
            or session.access_token is None
            or settings is None
            or sender is None
        ):
            logger.warning(
                "safety_state_sync_skipped_without_api_session",
                extra={"work_session_id": str(value.work_session_id)},
            )
            return
        worker = self._safety_state_delivery_worker
        if worker is not None and worker.isRunning():
            self._pending_safety_state_snapshot = value
            return
        self._start_safety_state_delivery(value, session.access_token)

    def _start_safety_state_delivery(
        self,
        snapshot: SafetyStateSnapshot,
        access_token: str,
    ) -> None:
        settings = self._settings
        sender = self._safety_state_sender
        if settings is None or sender is None:
            return
        worker = SafetyStateDeliveryWorker(
            sender,
            snapshot,
            access_token,
            maximum_attempts=settings.alert_delivery_max_attempts,
            retry_delay_seconds=settings.alert_delivery_retry_delay_seconds,
        )
        worker.delivered.connect(self._handle_safety_state_delivered)
        worker.delivery_failed.connect(self._handle_safety_state_delivery_failed)
        worker.finished.connect(
            partial(self._dispose_safety_state_delivery_worker, worker)
        )
        self._safety_state_delivery_worker = worker
        worker.start()

    @Slot(object)
    def _handle_safety_state_delivered(self, value: object) -> None:
        if not isinstance(value, SafetyStateDeliveryReceipt):
            return
        logger.info(
            "safety_state_synchronized",
            extra={
                "state": value.state.value,
                "active_conditions": value.active_conditions,
            },
        )

    @Slot(str)
    def _handle_safety_state_delivery_failed(self, message: str) -> None:
        logger.warning("safety_state_sync_failed", extra={"reason": message})

    def _dispose_safety_state_delivery_worker(
        self,
        worker: SafetyStateDeliveryWorker,
    ) -> None:
        if self._safety_state_delivery_worker is worker:
            self._safety_state_delivery_worker = None
        worker.deleteLater()
        pending = self._pending_safety_state_snapshot
        self._pending_safety_state_snapshot = None
        if pending is not None:
            self._handle_safety_state_snapshot(pending)

    def _shutdown_safety_state_delivery_worker(
        self,
        wait_timeout_ms: int = 5_000,
    ) -> None:
        worker = self._safety_state_delivery_worker
        if worker is not None:
            if worker.isRunning() and not worker.wait(wait_timeout_ms):
                worker.requestInterruption()
                logger.error("safety_state_delivery_worker_shutdown_timeout")
            self._safety_state_delivery_worker = None
            worker.deleteLater()
        pending = self._pending_safety_state_snapshot
        self._pending_safety_state_snapshot = None
        session = self._session_context.current
        sender = self._safety_state_sender
        if (
            pending is None
            or session is None
            or session.access_token is None
            or sender is None
        ):
            return
        try:
            sender.send_safety_state(pending, session.access_token)
        except SafetyStateDeliveryError as error:
            logger.warning(
                "safety_state_final_sync_failed",
                extra={"reason": str(error)},
            )

    def _dispose_alert_delivery_worker(self, worker: AlertDeliveryWorker) -> None:
        self._alert_delivery_workers.pop(worker.event_id, None)
        worker.deleteLater()
        pending = self._pending_alert_deliveries.pop(worker.event_id, None)
        session = self._session_context.current
        if pending is not None and session is not None and session.access_token is not None:
            self._start_alert_delivery(pending, session.access_token)

    def _shutdown_alert_delivery_workers(self, wait_timeout_ms: int = 5_000) -> None:
        self._pending_alert_deliveries.clear()
        workers = tuple(self._alert_delivery_workers.values())
        for worker in workers:
            worker.requestInterruption()
        for worker in workers:
            if worker.isRunning() and not worker.wait(wait_timeout_ms):
                logger.error(
                    "alert_delivery_worker_shutdown_timeout",
                    extra={"event_id": worker.event_id},
                )
                continue
            self._dispose_alert_delivery_worker(worker)

    @Slot(object)
    def handle_operation_start_authorized(self, value: object) -> None:
        """Create the local WorkSession from a typed one-shot authorization."""

        main_window = self._main_window
        if main_window is None or not isinstance(value, OperationStartAuthorization):
            logger.error("invalid_operation_start_authorization")
            return
        operation = main_window.safety_verification_page.operation
        if operation is None or operation.operation_id != value.operation_id:
            logger.warning(
                "operation_start_authorization_context_mismatch",
                extra={"operation_id": value.operation_id},
            )
            main_window.safety_verification_page.show_operation_start_rejected()
            return
        try:
            work_session = self._work_session_service.start(
                self._session_context.require_current(),
                operation,
                value,
            )
            main_window.show_active_operation(work_session, operation)
        except WorkSessionError as error:
            logger.warning(
                "local_work_session_start_rejected",
                extra={"operation_id": value.operation_id, "reason": str(error)},
            )
            main_window.safety_verification_page.show_operation_start_rejected()
        except Exception:
            self._work_session_service.interrupt_active()
            raise

    @Slot(str)
    def handle_work_session_finish_requested(self, session_id: str) -> None:
        """Complete the matching local WorkSession and return to operations."""

        main_window = self._main_window
        if main_window is None:
            return
        try:
            parsed_session_id = UUID(session_id)
            self._work_session_service.complete(parsed_session_id)
        except (ValueError, WorkSessionError) as error:
            logger.warning(
                "local_work_session_finish_rejected",
                extra={"reason": str(error)},
            )
            main_window.active_operation_page.show_finish_failure(
                "Não foi possível encerrar a operação localmente. Tente novamente."
            )
            return
        main_window.close_active_operation()
