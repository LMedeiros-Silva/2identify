from pathlib import Path

from PySide6.QtWidgets import QLabel

from app.controllers.operations_controller import OperationsController
from app.domain.operation import (
    ManualReferenceKind,
    Operation,
    OperationManual,
    RiskAreaReference,
)
from app.domain.risk_area import NormalizedPoint, RiskAreaGeometry
from app.services.manual_service import ManualService
from app.services.operation_service import OperationService
from app.ui.operations import OperationsPage, OperationsPageState


class StaticProvider:
    def list_operations(self) -> tuple[Operation, ...]:
        return (Operation(8, "Inspeção industrial"),)


class FailingProvider:
    def list_operations(self) -> tuple[Operation, ...]:
        raise OSError("offline")


class SingleOperationProvider:
    def __init__(self, operation: Operation) -> None:
        self._operation = operation

    def list_operations(self) -> tuple[Operation, ...]:
        return (self._operation,)


class RecordingLauncher:
    def __init__(self) -> None:
        self.received: Path | None = None

    def open_local_pdf(self, path: Path) -> bool:
        self.received = path
        return True


def test_operations_controller_loads_service_data_into_page(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(
        OperationService(StaticProvider()),
        page,
        source_notice="DADOS DE TESTE",
    )

    controller.load_operations()

    assert page.state is OperationsPageState.READY
    assert page.operations == (Operation(8, "Inspeção industrial"),)


def test_operations_controller_maps_provider_failure_to_safe_error_state(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(OperationService(FailingProvider()), page)

    controller.load_operations()

    assert page.state is OperationsPageState.ERROR


def test_operations_controller_resolves_selection_from_loaded_snapshot(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(OperationService(StaticProvider()), page)
    controller.load_operations()

    page.operation_selected.emit(8)

    assert page.selected_operation_id == 8
    assert page.findChild(QLabel, "operationDetailsName").text() == "Inspeção industrial"


def test_operations_controller_ignores_unknown_selection(qtbot, caplog) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(OperationService(StaticProvider()), page)
    controller.load_operations()

    page.operation_selected.emit(999)

    assert page.selected_operation_id is None
    assert "operation_selection_ignored_unknown_id" in caplog.text


def test_operations_controller_opens_selected_manual_through_service(
    qtbot,
    tmp_path: Path,
) -> None:
    manual = OperationManual("manual.pdf", ManualReferenceKind.LOCAL_FILE)
    operation = Operation(8, "Inspeção industrial", manual=manual)
    (tmp_path / "manual.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    launcher = RecordingLauncher()
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(
        OperationService(SingleOperationProvider(operation)),
        page,
        manual_service=ManualService(tmp_path, launcher),
    )
    controller.load_operations()
    page.operation_selected.emit(8)

    page.manual_requested.emit(8)

    assert launcher.received == (tmp_path / "manual.pdf").resolve()


def test_operations_controller_maps_missing_manual_to_safe_view_error(
    qtbot,
    tmp_path: Path,
) -> None:
    manual = OperationManual("missing.pdf", ManualReferenceKind.LOCAL_FILE)
    operation = Operation(8, "Inspeção industrial", manual=manual)
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(
        OperationService(SingleOperationProvider(operation)),
        page,
        manual_service=ManualService(tmp_path, RecordingLauncher()),
    )
    controller.load_operations()
    page.operation_selected.emit(8)

    page.manual_requested.emit(8)

    assert page.findChild(QLabel, "operationManualStatus").text() == "INDISPONÍVEL"
    assert "Não foi possível abrir" in page.findChild(
        QLabel, "operationManualError"
    ).text()


def test_operations_controller_forwards_validated_risk_area_intent(qtbot) -> None:
    risk_area = RiskAreaReference(
        31,
        "Linha de Produção A",
        RiskAreaGeometry(
            (
                NormalizedPoint(0.1, 0.6),
                NormalizedPoint(0.4, 0.3),
                NormalizedPoint(0.9, 0.7),
            )
        ),
        geometry_calibrated=True,
    )
    operation = Operation(8, "Inspeção industrial", risk_area=risk_area)
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(
        OperationService(SingleOperationProvider(operation)),
        page,
    )
    controller.load_operations()
    page.operation_selected.emit(8)

    with qtbot.waitSignal(controller.risk_area_requested, timeout=1_000) as emitted:
        page.risk_area_requested.emit(8)

    assert emitted.args == [risk_area]
    assert "zona calibrada" in page.findChild(
        QLabel,
        "operationRiskAreaNotice",
    ).text()


def test_operations_controller_ignores_risk_area_for_unknown_selection(
    qtbot,
    caplog,
) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(OperationService(StaticProvider()), page)
    controller.load_operations()

    page.risk_area_requested.emit(999)

    assert "risk_area_request_ignored_unknown_selection" in caplog.text


def test_operations_controller_forwards_selected_operation_for_safety_preparation(
    qtbot,
) -> None:
    operation = Operation(8, "Inspeção industrial")
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(
        OperationService(SingleOperationProvider(operation)),
        page,
    )
    controller.load_operations()
    page.operation_selected.emit(8)

    with qtbot.waitSignal(
        controller.safety_verification_requested,
        timeout=1_000,
    ) as emitted:
        page.safety_verification_requested.emit(8)

    assert emitted.args == [operation]


def test_operations_controller_ignores_safety_request_outside_selection(
    qtbot,
    caplog,
) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    controller = OperationsController(OperationService(StaticProvider()), page)
    controller.load_operations()

    page.safety_verification_requested.emit(8)

    assert "safety_verification_request_ignored_unknown_selection" in caplog.text
