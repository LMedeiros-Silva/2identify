"""Lifecycle controller for facial login."""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage

from app.core.config import AppSettings
from app.core.constants import PROJECT_ROOT
from app.domain.auth import OperatorIdentity
from app.ui.login import FaceLoginState, LoginWindow
from app.vision.camera import OpenCVCameraSession
from app.vision.face_auth.factory import build_local_face_authentication_pipeline
from app.workers.face_auth_worker import FaceAuthenticationWorker

logger = logging.getLogger(__name__)


class FaceLoginController(QObject):
    """Own a single biometric attempt and guarantee cooperative worker shutdown."""

    operator_authenticated = Signal(object)

    def __init__(self, settings: AppSettings, window: LoginWindow) -> None:
        super().__init__(window)
        self._settings = settings
        self._window = window
        self._worker: FaceAuthenticationWorker | None = None
        self._window.face_login_requested.connect(self.start)
        self._window.face_login_cancel_requested.connect(self.stop)

    @Slot()
    def start(self) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            self._window.show_face_authentication_error(
                "A tentativa anterior ainda está sendo finalizada. Aguarde um instante."
            )
            return

        self._dispose_finished_worker()
        self._window.set_face_authentication_state(
            FaceLoginState.STARTING,
            "Carregando câmera e modelos biométricos...",
        )
        worker = FaceAuthenticationWorker(
            camera_factory=partial(
                OpenCVCameraSession,
                source=self._settings.parsed_login_camera_source,
                width=self._settings.login_camera_width,
                height=self._settings.login_camera_height,
                open_timeout_ms=self._settings.login_camera_open_timeout_ms,
                read_timeout_ms=self._settings.login_camera_read_timeout_ms,
            ),
            pipeline_factory=partial(
                build_local_face_authentication_pipeline,
                self._settings,
            ),
            timeout_seconds=self._settings.face_auth_timeout_seconds,
            inference_fps=self._settings.face_auth_inference_fps,
            preview_fps=self._settings.face_auth_preview_fps,
            maximum_failed_reads=self._settings.login_camera_max_failed_reads,
        )
        worker.frame_ready.connect(self._window.update_face_frame)
        worker.pipeline_status_changed.connect(self._handle_pipeline_status)
        worker.operator_recognized.connect(self._handle_recognized)
        worker.authentication_failed.connect(self._handle_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("face_auth_attempt_started")
        worker.start()

    @Slot()
    def stop(self) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()

    def shutdown(self, wait_timeout_ms: int = 5_000) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.request_stop()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("face_auth_worker_shutdown_timeout")
        self._dispose_finished_worker()

    @Slot(str, str)
    def _handle_pipeline_status(self, _status: str, message: str) -> None:
        self._window.set_face_authentication_state(FaceLoginState.SCANNING, message)

    @Slot(object)
    def _handle_recognized(self, result: object) -> None:
        if not isinstance(result, OperatorIdentity):
            self._handle_failure("O reconhecedor retornou uma identidade inválida.", False)
            return

        portrait = self._load_registered_portrait(result.profile_photo_reference)
        self._window.show_operator_recognized(result, portrait)
        logger.info(
            "operator_face_authenticated",
            extra={
                "operator_id": result.operator_id,
                "confidence": round(result.confidence, 4),
                "authorization_mode": "local_development",
            },
        )
        self.operator_authenticated.emit(result)

    @Slot(str, bool)
    def _handle_failure(self, message: str, unavailable: bool) -> None:
        self._window.show_face_authentication_error(message, unavailable=unavailable)
        logger.warning(
            "operator_face_authentication_failed",
            extra={"unavailable": unavailable, "reason": message},
        )

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("face_auth_attempt_finished")

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None

    @staticmethod
    def _load_registered_portrait(reference: str | None) -> QImage | None:
        if not reference:
            return None
        path = Path(reference)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(PROJECT_ROOT) or not resolved_path.is_file():
            logger.warning("operator_profile_photo_reference_rejected")
            return None
        portrait = QImage(str(resolved_path))
        return None if portrait.isNull() else portrait
