"""Admin report filters and XLSX export action."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.admin_reports_service import ReportFilters


class ReportsPage(QWidget):
    export_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("reports_page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(16)
        title = QLabel("Relatórios")
        title.setObjectName("pagina_titulo")
        layout.addWidget(title)
        subtitle = QLabel("Exporte os alertas e ocorrências registrados pela API em Excel.")
        subtitle.setObjectName("pagina_subtitulo")
        layout.addWidget(subtitle)

        filters = QFormLayout()
        self.start_enabled = QCheckBox("Filtrar a partir de")
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_date.setCalendarPopup(True)
        start_row = QHBoxLayout()
        start_row.addWidget(self.start_enabled)
        start_row.addWidget(self.start_date)
        filters.addRow("Data inicial", start_row)
        self.end_enabled = QCheckBox("Filtrar até")
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        end_row = QHBoxLayout()
        end_row.addWidget(self.end_enabled)
        end_row.addWidget(self.end_date)
        filters.addRow("Data final", end_row)

        self.severity = QComboBox()
        self.severity.addItem("Todas", None)
        self.severity.addItem("Crítica", "critical")
        self.severity.addItem("Aviso", "warning")
        filters.addRow("Severidade", self.severity)
        self.sector_id = self._id_filter(filters, "ID setor")
        self.employee_id = self._id_filter(filters, "ID funcionário")
        self.operation_id = self._id_filter(filters, "ID operação")
        self.camera_id = self._id_filter(filters, "ID câmera")
        layout.addLayout(filters)

        self.export_button = QPushButton("Exportar XLSX")
        self.export_button.setObjectName("reports_export_button")
        self.export_button.clicked.connect(self._request_export)
        layout.addWidget(self.export_button)
        self.status = QLabel("O arquivo incluirá Resumo, Alertas, Ocorrências e EPIs.")
        self.status.setObjectName("reports_status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()

    @staticmethod
    def _id_filter(layout: QFormLayout, label: str) -> QSpinBox:
        field = QSpinBox()
        field.setRange(0, 2_147_483_647)
        field.setSpecialValueText("Todos")
        layout.addRow(label, field)
        return field

    def filters(self) -> ReportFilters:
        def selected_date(enabled: QCheckBox, value: QDateEdit) -> date | None:
            return value.date().toPython() if enabled.isChecked() else None

        return ReportFilters(
            date_from=selected_date(self.start_enabled, self.start_date),
            date_to=selected_date(self.end_enabled, self.end_date),
            sector_id=self.sector_id.value() or None,
            employee_id=self.employee_id.value() or None,
            operation_id=self.operation_id.value() or None,
            camera_id=self.camera_id.value() or None,
            severity=self.severity.currentData(),
        )

    def _request_export(self) -> None:
        try:
            filters = self.filters()
        except ValueError as error:
            self.show_error(str(error))
            return
        self.export_requested.emit(filters)

    def show_loading(self) -> None:
        self.export_button.setEnabled(False)
        self.status.setText("Preparando arquivo XLSX...")

    def show_success(self, path: str) -> None:
        self.export_button.setEnabled(True)
        self.status.setText(f"Relatório salvo em {path}")

    def show_error(self, message: str) -> None:
        self.export_button.setEnabled(True)
        self.status.setText(message)

    def show_cancelled(self) -> None:
        self.export_button.setEnabled(True)
        self.status.setText("Exportação cancelada.")
