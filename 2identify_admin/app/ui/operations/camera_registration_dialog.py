"""Authenticated camera registration dialog used by operation configuration."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.domain import CameraDraft, SectorOption


class CameraRegistrationDialog(QDialog):
    def __init__(self, sectors: tuple[SectorOption, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result_draft: CameraDraft | None = None
        self.setWindowTitle("Cadastrar câmera")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        title = QLabel("Nova câmera")
        title.setObjectName("risk_editor_title")
        layout.addWidget(title)
        instructions = QLabel(
            "Informe 0 para a webcam principal, 1 para a segunda câmera USB, "
            "ou use uma URL RTSP/HTTP."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex.: Câmera da linha A")
        form.addRow("Nome*", self.name_edit)
        self.source_edit = QLineEdit("0")
        self.source_edit.setPlaceholderText("0 ou rtsp://...")
        form.addRow("Fonte*", self.source_edit)
        self.sector_combo = QComboBox()
        for sector in sectors:
            self.sector_combo.addItem(sector.name, sector.id)
        form.addRow("Setor*", self.sector_combo)
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(70)
        self.description_edit.setPlaceholderText("Descrição opcional")
        form.addRow("Descrição", self.description_edit)
        layout.addLayout(form)

        self.feedback = QLabel()
        self.feedback.setStyleSheet("color: #B42318;")
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        layout.addWidget(self.feedback)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText("Cadastrar câmera")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        sector_id = self.sector_combo.currentData()
        try:
            self.result_draft = CameraDraft(
                name=self.name_edit.text(),
                description=self.description_edit.toPlainText(),
                stream_source=self.source_edit.text(),
                sector_id=int(sector_id) if isinstance(sector_id, int) else 0,
            )
        except ValueError as error:
            self.feedback.setText(str(error))
            self.feedback.show()
            return
        self.accept()


__all__ = ["CameraRegistrationDialog"]
