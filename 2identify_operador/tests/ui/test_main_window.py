from datetime import UTC, datetime
from uuid import UUID

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QStackedWidget

from app.core.session import AuthenticationMethod, OperatorSession
from app.domain.operation import Operation, PpeRequirement, RiskAreaReference
from app.domain.work_session import WorkSession, WorkSessionStatus
from app.ui.active import ActiveOperationPage
from app.ui.components.sidebar import WORKS_ROUTE, Sidebar
from app.ui.main import MainWindow
from app.ui.operations import OperationsPage, OperationsPageState
from app.ui.safety import SafetyVerificationPage


@pytest.mark.parametrize(
    ("authentication_method", "expected_label"),
    [
        (AuthenticationMethod.FACE_ID, "Face ID"),
        (AuthenticationMethod.CREDENTIALS, "Credenciais"),
    ],
)
def test_main_window_presents_real_authenticated_session(
    qtbot,
    authentication_method: AuthenticationMethod,
    expected_label: str,
) -> None:
    session = OperatorSession(
        operator_id=15,
        operator_name="João Silva",
        login_time=datetime(2026, 8, 16, 13, 30, tzinfo=UTC),
        authentication_method=authentication_method,
    )
    window = MainWindow(session=session, app_version="0.1.0")
    qtbot.addWidget(window)
    window.show()

    assert window.session is session
    assert window.findChild(QLabel, "mainOperatorName").text() == "João Silva"
    assert window.findChild(QLabel, "mainOperatorDetail").text() == (
        f"Operador #15 · {expected_label}"
    )
    assert window.findChild(QLabel, "mainSessionBadge").text() == "SESSÃO ATIVA"
    assert window.findChild(QLabel, "operationsTitle").text() == "Operações"


def test_main_window_exposes_initial_stack_without_fake_operational_data(qtbot) -> None:
    session = OperatorSession(
        operator_id=15,
        operator_name="João Silva",
        login_time=datetime(2026, 8, 16, 13, 30, tzinfo=UTC),
        authentication_method=AuthenticationMethod.FACE_ID,
    )
    window = MainWindow(session=session, app_version="0.1.0")
    qtbot.addWidget(window)
    window.show()

    stack = window.findChild(QStackedWidget, "mainPageStack")
    assert stack.count() == 3
    assert isinstance(stack.currentWidget(), OperationsPage)
    assert stack.currentWidget() is window.operations_page
    assert window.operations_page.state is OperationsPageState.NOT_LOADED
    assert window.findChild(QLabel, "operationsListStatus").text() == "NÃO CARREGADO"


def test_main_window_integrates_sidebar_and_forwards_logout(qtbot) -> None:
    session = OperatorSession(
        operator_id=15,
        operator_name="João Silva",
        login_time=datetime(2026, 8, 16, 13, 30, tzinfo=UTC),
        authentication_method=AuthenticationMethod.FACE_ID,
    )
    window = MainWindow(session=session, app_version="0.1.0")
    qtbot.addWidget(window)
    window.show()
    sidebar = window.findChild(Sidebar, "mainSidebar")
    logout_button = sidebar.findChild(QPushButton, "sidebarLogoutButton")

    assert sidebar.selected_route == WORKS_ROUTE
    with qtbot.waitSignal(window.logout_requested, timeout=1_000):
        qtbot.mouseClick(logout_button, Qt.MouseButton.LeftButton)


def test_main_window_navigates_to_safety_preparation_and_back(qtbot) -> None:
    session = OperatorSession(
        operator_id=15,
        operator_name="João Silva",
        login_time=datetime(2026, 8, 16, 13, 30, tzinfo=UTC),
        authentication_method=AuthenticationMethod.FACE_ID,
    )
    window = MainWindow(session=session, app_version="0.1.0")
    qtbot.addWidget(window)
    window.show()
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete de segurança"),),
        risk_area=RiskAreaReference(7, "Linha de Produção A"),
    )
    stack = window.findChild(QStackedWidget, "mainPageStack")

    window.show_safety_verification(operation)

    assert isinstance(stack.currentWidget(), SafetyVerificationPage)
    assert stack.currentWidget() is window.safety_verification_page
    assert window.safety_verification_page.operation is operation
    assert window.findChild(QLabel, "mainPageTitle").text() == (
        "Verificação de segurança"
    )
    assert window.findChild(QLabel, "mainPageContext").text() == (
        "Preparação para liberação"
    )

    back_button = window.safety_verification_page.findChild(
        QPushButton,
        "safetyBackButton",
    )
    qtbot.mouseClick(back_button, Qt.MouseButton.LeftButton)

    assert stack.currentWidget() is window.operations_page
    assert window.findChild(QLabel, "mainPageTitle").text() == "Trabalhos"
    assert window.findChild(QLabel, "mainPageContext").text() == (
        "Ambiente do operador"
    )


def test_main_window_presents_and_guards_active_work_session(qtbot) -> None:
    started_at = datetime(2026, 8, 17, 13, 30, tzinfo=UTC)
    session = OperatorSession(
        operator_id=15,
        operator_name="João Silva",
        login_time=started_at,
        authentication_method=AuthenticationMethod.FACE_ID,
    )
    window = MainWindow(session=session, app_version="0.1.0")
    qtbot.addWidget(window)
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
    )
    work_session = WorkSession(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),
        operator_id=15,
        operation_id=41,
        camera_id=None,
        risk_area_id=None,
        verified_ppe_ids=(1,),
        safety_verified_at=started_at,
        ppe_sample_count=8,
        ppe_window_size=8,
        started_at=started_at,
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
    )
    stack = window.findChild(QStackedWidget, "mainPageStack")

    window.show_active_operation(work_session, operation)

    assert isinstance(stack.currentWidget(), ActiveOperationPage)
    assert window.active_operation_page.work_session is work_session
    assert window.findChild(QLabel, "mainPageTitle").text() == "Operação ativa"
    window.show_operations()
    assert stack.currentWidget() is window.active_operation_page

    window.close_active_operation()
    assert stack.currentWidget() is window.operations_page
