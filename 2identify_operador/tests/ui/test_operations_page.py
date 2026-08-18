import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSplitter

from app.domain.operation import (
    ManualReferenceKind,
    Operation,
    OperationManual,
    PpeRequirement,
    RiskAreaReference,
)
from app.domain.risk_area import NormalizedPoint, RiskAreaGeometry
from app.ui.components import CameraFrameView
from app.ui.operations import OperationsPage, OperationsPageState


def _risk_geometry() -> RiskAreaGeometry:
    return RiskAreaGeometry(
        (
            NormalizedPoint(0.1, 0.6),
            NormalizedPoint(0.4, 0.3),
            NormalizedPoint(0.9, 0.7),
        )
    )


def test_operations_page_starts_without_inventing_operational_data(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    page.show()

    assert page.state is OperationsPageState.NOT_LOADED
    assert page.findChild(QSplitter, "operationsSplitter") is not None
    assert page.findChild(QFrame, "operationsListPanel") is not None
    assert page.findChild(QFrame, "operationDetailsPanel") is not None
    assert page.findChild(QLabel, "operationsListStatus").text() == "NÃO CARREGADO"
    assert page.findChild(QLabel, "operationsStateTitle").text() == (
        "Aguardando fonte de operações"
    )
    assert page.findChild(QLabel, "operationDetailsEmptyTitle").text() == (
        "Selecione uma operação"
    )
    assert page.findChildren(QPushButton, "operationListButton") == []


@pytest.mark.parametrize(
    ("state", "expected_badge", "expected_title"),
    [
        (OperationsPageState.LOADING, "CARREGANDO", "Carregando operações"),
        (OperationsPageState.EMPTY, "LISTA VAZIA", "Nenhuma operação disponível"),
        (
            OperationsPageState.ERROR,
            "INDISPONÍVEL",
            "Não foi possível carregar as operações",
        ),
    ],
)
def test_operations_page_presents_explicit_data_states(
    qtbot,
    state: OperationsPageState,
    expected_badge: str,
    expected_title: str,
) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)

    page.set_list_state(state)

    state_frame = page.findChild(QFrame, "operationsListState")
    assert page.state is state
    assert state_frame.property("state") == state.value
    assert page.findChild(QLabel, "operationsListStatus").text() == expected_badge
    assert page.findChild(QLabel, "operationsStateTitle").text() == expected_title


def test_operations_page_accepts_a_safe_error_message(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)

    page.set_list_state(
        OperationsPageState.ERROR,
        "O serviço de operações não respondeu. Tente novamente mais tarde.",
    )

    assert page.findChild(QLabel, "operationsStateDescription").text() == (
        "O serviço de operações não respondeu. Tente novamente mais tarde."
    )


def test_operations_page_renders_a_dynamic_operation_list(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    operations = (Operation(10, "Manutenção"), Operation(22, "Soldagem"))

    page.set_operations(operations, source_notice="DADOS LOCAIS DE DESENVOLVIMENTO")

    buttons = page.findChildren(QPushButton, "operationListButton")
    assert page.state is OperationsPageState.READY
    assert page.operations == operations
    assert [button.text() for button in buttons] == ["Manutenção", "Soldagem"]
    assert page.findChild(QLabel, "operationsListStatus").text() == "2 DISPONÍVEIS"
    source_notice = page.findChild(QLabel, "operationsSourceNotice")
    assert source_notice.text() == "DADOS LOCAIS DE DESENVOLVIMENTO"
    assert source_notice.isVisibleTo(page)


def test_operations_page_emits_selected_operation_identifier(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    page.set_operations((Operation(10, "Manutenção"), Operation(22, "Soldagem")))
    button = page.findChildren(QPushButton, "operationListButton")[1]

    with qtbot.waitSignal(page.operation_selected, timeout=1_000) as emitted:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert emitted.args == [22]


def test_operations_page_maps_an_empty_result_to_empty_state(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)

    page.set_operations(())

    assert page.state is OperationsPageState.EMPTY
    assert page.operations == ()


def test_operations_page_highlights_and_presents_selected_operation(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    operations = (
        Operation(10, "Manutenção", "Manutenção preventiva dos equipamentos."),
        Operation(
            22,
            "Soldagem",
            "Reparo de componentes metálicos.",
            required_ppe=(
                PpeRequirement(1, "Capacete de segurança"),
                PpeRequirement(2, "Luvas de proteção"),
            ),
        ),
    )
    page.set_operations(operations)

    page.show_operation_details(operations[1])

    buttons = page.findChildren(QPushButton, "operationListButton")
    assert page.selected_operation_id == 22
    assert [button.property("selected") for button in buttons] == [False, True]
    assert page.findChild(QLabel, "operationDetailsStatus").text() == "SELECIONADA"
    assert page.findChild(QLabel, "operationDetailsCode").text() == "CÓDIGO #22"
    assert page.findChild(QLabel, "operationDetailsName").text() == "Soldagem"
    assert page.findChild(QLabel, "operationDetailsDescription").text() == (
        "Reparo de componentes metálicos."
    )
    assert page.findChild(QLabel, "operationDetailsActiveBadge").text() == "ATIVA"
    assert page.displayed_required_ppe == operations[1].required_ppe
    assert page.findChild(QLabel, "operationPpeCount").text() == "2 OBRIGATÓRIOS"
    ppe_names = page.findChildren(QLabel, "operationPpeRequirementName")
    assert [label.text() for label in ppe_names] == [
        "Capacete de segurança",
        "Luvas de proteção",
    ]
    assert all(
        label.text() != "DETECTADO"
        for label in page.findChildren(QLabel, "operationPpeRequiredBadge")
    )


def test_operations_page_uses_honest_fallback_and_resets_details(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    operation = Operation(10, "Manutenção")
    page.set_operations((operation,))
    page.show_operation_details(operation)

    assert page.findChild(QLabel, "operationDetailsDescription").text() == (
        "Descrição não informada para esta operação."
    )
    assert page.findChild(QLabel, "operationPpeCount").text() == "0 OBRIGATÓRIOS"
    assert page.findChild(QLabel, "operationPpeEmptyState").isVisibleTo(page)
    assert page.findChild(QLabel, "operationManualStatus").text() == "NÃO CONFIGURADO"
    assert not page.findChild(QPushButton, "operationManualButton").isEnabled()
    assert page.findChild(QLabel, "operationRiskAreaStatus").text() == "NÃO CONFIGURADA"
    assert not page.findChild(QPushButton, "operationRiskAreaButton").isEnabled()

    page.set_operations((Operation(30, "Inspeção"),))

    assert page.selected_operation_id is None
    assert page.displayed_required_ppe == ()
    assert page.findChild(QLabel, "operationDetailsStatus").text() == "AGUARDANDO SELEÇÃO"
    assert page.findChild(QLabel, "operationDetailsEmptyTitle").isVisibleTo(page)


def test_operations_page_rejects_details_outside_current_snapshot(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    page.set_operations((Operation(10, "Manutenção"),))

    with pytest.raises(ValueError, match="não pertence"):
        page.show_operation_details(Operation(99, "Operação externa"))


def test_operations_page_presents_and_emits_configured_manual(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    manual = OperationManual(
        "development/manual.pdf",
        ManualReferenceKind.LOCAL_FILE,
        title="Manual controlado da operação",
    )
    operation = Operation(10, "Manutenção", manual=manual)
    page.set_operations((operation,))
    page.show_operation_details(operation)
    manual_button = page.findChild(QPushButton, "operationManualButton")

    assert page.findChild(QLabel, "operationManualStatus").text() == "CONFIGURADO"
    assert page.findChild(QLabel, "operationManualTitle").text() == (
        "Manual controlado da operação"
    )
    assert manual_button.isEnabled()
    with qtbot.waitSignal(page.manual_requested, timeout=1_000) as emitted:
        qtbot.mouseClick(manual_button, Qt.MouseButton.LeftButton)

    assert emitted.args == [10]


def test_operations_page_presents_manual_open_failure(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    manual = OperationManual("manual.pdf", ManualReferenceKind.LOCAL_FILE)
    operation = Operation(10, "Manutenção", manual=manual)
    page.set_operations((operation,))
    page.show_operation_details(operation)

    page.show_manual_error("Não foi possível abrir o manual.")

    assert page.findChild(QLabel, "operationManualStatus").text() == "INDISPONÍVEL"
    assert page.findChild(QLabel, "operationManualError").text() == (
        "Não foi possível abrir o manual."
    )


def test_operations_page_presents_and_emits_associated_risk_area(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    risk_area = RiskAreaReference(
        31,
        "Linha de Produção A",
        _risk_geometry(),
        geometry_calibrated=True,
    )
    operation = Operation(10, "Manutenção", risk_area=risk_area)
    page.set_operations((operation,))
    page.show_operation_details(operation)
    risk_area_button = page.findChild(QPushButton, "operationRiskAreaButton")

    assert page.displayed_risk_area is risk_area
    assert page.findChild(QLabel, "operationRiskAreaStatus").text() == "DELIMITADA"
    assert page.findChild(QLabel, "operationRiskAreaName").text() == (
        "Linha de Produção A"
    )
    assert risk_area_button.isEnabled()
    with qtbot.waitSignal(page.risk_area_requested, timeout=1_000) as emitted:
        qtbot.mouseClick(risk_area_button, Qt.MouseButton.LeftButton)

    assert emitted.args == [10]


def test_operations_page_visualizes_configured_risk_area(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    risk_area = RiskAreaReference(
        31,
        "Linha de Produção A",
        _risk_geometry(),
        geometry_calibrated=True,
    )
    operation = Operation(10, "Manutenção", risk_area=risk_area)
    page.set_operations((operation,))
    page.show_operation_details(operation)

    page.show_risk_area(risk_area)

    notice = page.findChild(QLabel, "operationRiskAreaNotice")
    preview = page.findChild(CameraFrameView, "operationRiskAreaPreview")
    assert "zona calibrada" in notice.text()
    assert notice.isVisibleTo(page)
    assert preview.isVisibleTo(page)
    assert preview.risk_zone_labels == ("Linha de Produção A",)


def test_operations_page_does_not_invent_missing_risk_geometry(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    risk_area = RiskAreaReference(31, "Linha de Produção A")
    operation = Operation(10, "Manutenção", risk_area=risk_area)
    page.set_operations((operation,))
    page.show_operation_details(operation)

    risk_area_button = page.findChild(QPushButton, "operationRiskAreaButton")
    assert not risk_area_button.isEnabled()
    assert page.findChild(QLabel, "operationRiskAreaStatus").text() == (
        "SEM GEOMETRIA"
    )
    assert "não há um polígono" in page.findChild(
        QLabel,
        "operationRiskAreaNotice",
    ).text()


def test_operations_page_marks_uncalibrated_geometry_as_demonstrative(qtbot) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    risk_area = RiskAreaReference(31, "Linha de Produção A", _risk_geometry())
    operation = Operation(10, "Manutenção", risk_area=risk_area)
    page.set_operations((operation,))
    page.show_operation_details(operation)

    assert page.findChild(QLabel, "operationRiskAreaStatus").text() == (
        "DEMONSTRAÇÃO"
    )
    page.show_risk_area(risk_area)
    assert "não calibrada" in page.findChild(
        QLabel,
        "operationRiskAreaNotice",
    ).text()


def test_operations_page_requests_preparation_without_claiming_work_started(
    qtbot,
) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    operation = Operation(10, "Manutenção")
    page.set_operations((operation,))
    page.show_operation_details(operation)
    start_button = page.findChild(QPushButton, "operationSafetyStartButton")
    description = page.findChild(QLabel, "operationSafetyStartDescription")

    assert start_button.text() == "COMEÇAR TRABALHO"
    assert start_button.isEnabled()
    assert "não será iniciada" in description.text()
    with qtbot.waitSignal(
        page.safety_verification_requested,
        timeout=1_000,
    ) as emitted:
        qtbot.mouseClick(start_button, Qt.MouseButton.LeftButton)

    assert emitted.args == [10]


def test_operations_page_disables_safety_preparation_for_inactive_operation(
    qtbot,
) -> None:
    page = OperationsPage()
    qtbot.addWidget(page)
    operation = Operation(10, "Manutenção", active=False)
    page.set_operations((operation,))

    page.show_operation_details(operation)

    start_button = page.findChild(QPushButton, "operationSafetyStartButton")
    assert start_button.text() == "OPERAÇÃO INATIVA"
    assert not start_button.isEnabled()
