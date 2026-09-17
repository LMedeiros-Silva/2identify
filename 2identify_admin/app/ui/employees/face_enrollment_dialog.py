"""Guided frontal/left/right Face ID capture for one employee."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.core.config import Settings
from app.domain.employees import FaceTemplateDraft
from app.services.face_enrollment import FaceAngle, FaceCaptureError, combine_samples
from app.workers.face_capture_worker import FaceCaptureWorker


class FaceEnrollmentDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        parent=None,
        *,
        worker_factory: Callable[..., FaceCaptureWorker] = FaceCaptureWorker,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cadastrar Face ID")
        self.setMinimumSize(640, 560)
        self._settings = settings
        self._worker_factory = worker_factory
        self._worker: FaceCaptureWorker | None = None
        self._samples: dict[FaceAngle, np.ndarray] = {}
        self.template: FaceTemplateDraft | None = None

        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Capture exatamente um rosto, com boa luz e nitidez: "
            "frontal, voltado à esquerda e à direita na imagem. "
            "Você pode repetir qualquer captura."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.preview = QLabel("Webcam desligada")
        self.preview.setObjectName("employee_face_preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(320)
        layout.addWidget(self.preview)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Índice USB nesta estação:"))
        self.camera_index = QSpinBox()
        self.camera_index.setRange(0, 20)
        self.camera_index.setObjectName("employee_face_camera_index")
        source_row.addWidget(self.camera_index)
        self.start_button = QPushButton("Abrir webcam")
        self.start_button.clicked.connect(self._toggle_camera)
        source_row.addWidget(self.start_button)
        layout.addLayout(source_row)

        capture_row = QHBoxLayout()
        self.capture_buttons: dict[FaceAngle, QPushButton] = {}
        for angle, label in (
            (FaceAngle.FRONTAL, "Capturar frontal"),
            (FaceAngle.ESQUERDA, "Capturar esquerda"),
            (FaceAngle.DIREITA, "Capturar direita"),
        ):
            button = QPushButton(label)
            button.setObjectName(f"capture_{angle.value}")
            button.setEnabled(False)
            button.clicked.connect(lambda _checked=False, selected=angle: self._capture(selected))
            capture_row.addWidget(button)
            self.capture_buttons[angle] = button
        layout.addLayout(capture_row)

        self.status = QLabel("Abra a webcam para iniciar.")
        self.status.setObjectName("employee_face_status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.save_button = QPushButton("Usar Face ID")
        self.save_button.setObjectName("employee_face_use")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.accept)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def _toggle_camera(self) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            self.status.setText("Fechando webcam...")
            return
        if worker is not None:
            return
        worker = self._worker_factory(
            self.camera_index.value(),
            Path(self._settings.face_detector_model_path),
            Path(self._settings.face_recognition_model_path),
        )
        self._worker = worker
        worker.ready.connect(self._on_ready)
        worker.preview_ready.connect(self._on_preview)
        worker.sample_captured.connect(self._on_sample)
        worker.status.connect(self.status.setText)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_finished)
        self.start_button.setEnabled(False)
        self.status.setText("Abrindo webcam e modelos YuNet/SFace...")
        worker.start()

    @Slot()
    def _on_ready(self) -> None:
        self.start_button.setEnabled(True)
        self.start_button.setText("Parar webcam")
        for button in self.capture_buttons.values():
            button.setEnabled(True)
        self.status.setText("Webcam pronta. Faça a captura frontal.")

    @Slot(object)
    def _on_preview(self, value: object) -> None:
        if not isinstance(value, QImage):
            return
        pixmap = QPixmap.fromImage(value)
        self.preview.setPixmap(pixmap.scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    @Slot(object, object)
    def _on_sample(self, angle: object, embedding: object) -> None:
        if not isinstance(angle, FaceAngle) or not isinstance(embedding, tuple):
            return
        self._samples[angle] = np.asarray(embedding, dtype=np.float32)
        self.capture_buttons[angle].setText(f"{angle.value.capitalize()} ✓ Repetir")
        self.status.setText(f"Captura {angle.value} válida. {len(self._samples)}/3 prontas.")
        self.save_button.setEnabled(frozenset(self._samples) == frozenset(FaceAngle))

    def _capture(self, angle: FaceAngle) -> None:
        worker = self._worker
        if worker is None or not worker.isRunning():
            self.status.setText("Abra a webcam antes de capturar.")
            return
        worker.request_capture(angle)
        self.status.setText(f"Validando captura {angle.value}...")

    @Slot(str)
    def _on_failure(self, message: str) -> None:
        self.status.setText(message)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        if worker is not None and not worker.isRunning():
            worker.deleteLater()
            self._worker = None
        self.start_button.setEnabled(True)
        self.start_button.setText("Abrir webcam")
        for button in self.capture_buttons.values():
            button.setEnabled(False)
        self.preview.clear()
        self.preview.setText("Webcam desligada")

    def _release_camera(self) -> bool:
        worker = self._worker
        if worker is None:
            return True
        worker.request_stop()
        if worker.isRunning() and not worker.wait(5_000):
            self.status.setText("A webcam ainda está fechando. Tente novamente.")
            return False
        return True

    def accept(self) -> None:
        try:
            template = combine_samples(self._samples)
        except FaceCaptureError as error:
            self.status.setText(str(error))
            return
        if not self._release_camera():
            return
        self.template = template
        super().accept()

    def reject(self) -> None:
        if self._release_camera():
            super().reject()


__all__ = ["FaceEnrollmentDialog"]
