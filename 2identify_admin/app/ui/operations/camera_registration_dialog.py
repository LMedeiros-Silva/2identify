"""Authenticated camera registration dialog used by operation configuration."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
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

from app.domain import CameraDraft, ManagedCamera, SectorOption
from app.domain.camera_source import CameraSourceType, parse_camera_source


class CameraRegistrationDialog(QDialog):
    def __init__(
        self,
        sectors: tuple[SectorOption, ...],
        parent: QWidget | None = None,
        *,
        existing: ManagedCamera | None = None,
    ) -> None:
        super().__init__(parent)
        self.result_draft: CameraDraft | None = None
        self.setWindowTitle("Editar câmera" if existing else "Cadastrar câmera")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        title = QLabel("Editar câmera" if existing else "Nova câmera")
        title.setObjectName("risk_editor_title")
        layout.addWidget(title)
        instructions = QLabel(
            "USB: o índice é referência local da estação. IP: use URL RTSP/HTTP(S) "
            "sem credenciais; configure a fonte privada no .env do Operator."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex.: Câmera da linha A")
        form.addRow("Nome*", self.name_edit)
        self.type_combo = QComboBox()
        self.type_combo.addItem("USB local", CameraSourceType.USB)
        self.type_combo.addItem("IP / rede", CameraSourceType.IP)
        self.type_combo.currentIndexChanged.connect(self._update_source_hint)
        form.addRow("Tipo*", self.type_combo)
        self.source_edit = QLineEdit()
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
        self.active_check = QCheckBox("Câmera ativa")
        self.active_check.setChecked(existing.active if existing else True)
        form.addRow("Status", self.active_check)
        layout.addLayout(form)

        if existing is not None:
            self.name_edit.setText(existing.name)
            self.source_edit.setText(existing.stream_source)
            self.description_edit.setPlainText(existing.description or "")
            self.type_combo.setCurrentIndex(
                self.type_combo.findData(parse_camera_source(existing.stream_source))
            )
            self.sector_combo.setCurrentIndex(self.sector_combo.findData(existing.sector_id))

        self.feedback = QLabel()
        self.feedback.setStyleSheet("color: #B42318;")
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        layout.addWidget(self.feedback)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText("Salvar câmera" if existing else "Cadastrar câmera")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        sector_id = self.sector_combo.currentData()
        try:
            if parse_camera_source(self.source_edit.text()) != self.type_combo.currentData():
                raise ValueError("A fonte não corresponde ao tipo de câmera selecionado")
            self.result_draft = CameraDraft(
                name=self.name_edit.text(),
                description=self.description_edit.toPlainText(),
                stream_source=self.source_edit.text(),
                sector_id=int(sector_id) if isinstance(sector_id, int) else 0,
                active=self.active_check.isChecked(),
            )
        except ValueError as error:
            self.feedback.setText(str(error))
            self.feedback.show()
            return
        self.accept()

    def _update_source_hint(self) -> None:
        if self.type_combo.currentData() == CameraSourceType.USB:
            self.source_edit.setPlaceholderText("Índice USB local, ex.: 0")
        else:
            self.source_edit.setPlaceholderText("rtsp://host/path ou https://host/path")


__all__ = ["CameraRegistrationDialog"]
