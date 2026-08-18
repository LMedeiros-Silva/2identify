from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QStackedWidget

from app.controllers.application_controller import ApplicationController
from app.core.config import AppSettings
from app.core.session import AuthenticationMethod, OperatorSessionContext
from app.domain import (
    CredentialAuthenticationResult,
    OperationStartAuthorization,
    OperatorIdentity,
    PpeRequirement,
    WorkSessionStatus,
)
from app.domain.operation import Operation
from app.providers import MockOperationProvider
from app.services.operation_service import OperationService
from app.ui.active import ActiveOperationPage
from app.ui.login import LoginWindow
from app.ui.login.credential_login_panel import CredentialLoginPanel
from app.ui.login.face_login_panel import CameraPreview, FaceLoginPanel
from app.ui.operations import OperationsPageState
from app.ui.safety import SafetyVerificationPage


def _setup_controller(
    qtbot,
    operation_service: OperationService | None = None,
) -> tuple[LoginWindow, OperatorSessionContext, ApplicationController]:
    login_window = LoginWindow(AppSettings(_env_file=None))
    # The offscreen Qt plugin is unstable when repeatedly rasterizing custom camera
    # previews across unrelated UI tests. Painting itself is covered by login tests.
    login_window.findChild(CameraPreview, "faceCameraPreview").setUpdatesEnabled(False)
    session_context = OperatorSessionContext()
    controller = ApplicationController(
        session_context,
        login_window,
        "0.1.0",
        operation_service=operation_service,
        operations_source_notice=(
            "DADOS LOCAIS DE DESENVOLVIMENTO" if operation_service is not None else None
        ),
    )
    qtbot.addWidget(login_window)
    login_window.show()
    return login_window, session_context, controller


def test_face_authentication_opens_main_window_and_hides_login(qtbot) -> None:
    login_window, session_context, controller = _setup_controller(qtbot)

    controller.handle_face_authentication(
        OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    )

    main_window = controller.main_window
    assert main_window is not None
    qtbot.addWidget(main_window)
    assert main_window.isVisible()
    assert not login_window.isVisible()
    assert session_context.require_current().authentication_method is AuthenticationMethod.FACE_ID
    controller.handle_logout()


def test_credential_authentication_preserves_token_and_opens_main_window(qtbot) -> None:
    login_window, session_context, controller = _setup_controller(qtbot)

    controller.handle_credential_authentication(
        CredentialAuthenticationResult(
            operator_id=22,
            name="Ana Lima",
            access_token="token-confidencial",
        )
    )

    main_window = controller.main_window
    assert main_window is not None
    qtbot.addWidget(main_window)
    assert main_window.isVisible()
    assert not login_window.isVisible()
    session = session_context.require_current()
    assert session.authentication_method is AuthenticationMethod.CREDENTIALS
    assert session.access_token == "token-confidencial"
    controller.handle_logout()


def test_second_authentication_does_not_replace_active_session_or_window(qtbot) -> None:
    _login_window, session_context, controller = _setup_controller(qtbot)
    controller.handle_face_authentication(
        OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    )
    first_window = controller.main_window
    assert first_window is not None
    qtbot.addWidget(first_window)

    controller.handle_face_authentication(
        OperatorIdentity(operator_id=22, name="Ana Lima", confidence=0.97)
    )

    assert controller.main_window is first_window
    assert session_context.require_current().operator_id == 15
    controller.handle_logout()


def test_logout_closes_session_and_restores_clean_primary_login(qtbot) -> None:
    login_window, session_context, controller = _setup_controller(qtbot)
    login_window.show_credential_login()
    credential_panel = login_window.findChild(CredentialLoginPanel, "credentialLoginPanel")
    username = credential_panel.findChild(QLineEdit, "usernameInput")
    login_button = credential_panel.findChild(QPushButton, "loginButton")
    username.setText("operador.15")
    login_window.show_credential_authentication_success("Acesso autorizado.")
    controller.handle_credential_authentication(
        CredentialAuthenticationResult(15, "João Silva", "token-confidencial")
    )
    main_window = controller.main_window
    assert main_window is not None
    qtbot.addWidget(main_window)

    main_window.logout_requested.emit()

    assert controller.main_window is None
    assert session_context.current is None
    assert login_window.isVisible()
    stack = login_window.findChild(QStackedWidget, "authenticationStack")
    face_panel = login_window.findChild(FaceLoginPanel, "faceLoginPanel")
    assert stack.currentWidget() is face_panel
    assert username.text() == ""
    assert login_button.text() == "ENTRAR NO SISTEMA"
    assert login_button.isEnabled()


def test_authenticated_transition_loads_the_configured_operation_source(qtbot) -> None:
    operation = Operation(41, "Inspeção de segurança")
    service = OperationService(MockOperationProvider((operation,)))
    _login_window, _session_context, controller = _setup_controller(qtbot, service)

    controller.handle_face_authentication(
        OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    )

    main_window = controller.main_window
    assert main_window is not None
    qtbot.addWidget(main_window)
    assert main_window.operations_page.state is OperationsPageState.READY
    assert main_window.operations_page.operations == (operation,)

    operation_button = main_window.operations_page.findChild(
        QPushButton, "operationListButton"
    )
    qtbot.mouseClick(operation_button, Qt.MouseButton.LeftButton)

    assert main_window.operations_page.selected_operation_id == 41
    assert main_window.operations_page.findChild(QLabel, "operationDetailsName").text() == (
        "Inspeção de segurança"
    )

    start_button = main_window.operations_page.findChild(
        QPushButton,
        "operationSafetyStartButton",
    )
    qtbot.mouseClick(start_button, Qt.MouseButton.LeftButton)

    stack = main_window.findChild(QStackedWidget, "mainPageStack")
    assert isinstance(stack.currentWidget(), SafetyVerificationPage)
    assert main_window.safety_verification_page.operation is operation
    assert main_window.safety_verification_page.findChild(
        QLabel,
        "safetyReleaseTitle",
    ).text() == "OPERAÇÃO NÃO LIBERADA"
    controller.handle_logout()


def test_safety_authorization_creates_and_completes_local_work_session(qtbot) -> None:
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
    )
    service = OperationService(MockOperationProvider((operation,)))
    _login_window, _session_context, controller = _setup_controller(qtbot, service)
    controller.handle_face_authentication(
        OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    )
    main_window = controller.main_window
    assert main_window is not None
    qtbot.addWidget(main_window)
    main_window.show_safety_verification(operation)
    authorization = OperationStartAuthorization(
        operation_id=41,
        verified_ppe_ids=(1,),
        sample_count=8,
        window_size=8,
        authorized_at=datetime.now(UTC),
    )

    controller.handle_operation_start_authorized(authorization)

    active = controller.work_session_service.require_current()
    stack = main_window.findChild(QStackedWidget, "mainPageStack")
    assert isinstance(stack.currentWidget(), ActiveOperationPage)
    assert active.operator_id == 15
    assert active.operation_id == 41
    finish_button = main_window.active_operation_page.findChild(
        QPushButton,
        "activeFinishButton",
    )
    qtbot.mouseClick(finish_button, Qt.MouseButton.LeftButton)

    assert controller.work_session_service.current is None
    assert controller.work_session_service.last_finished.status is (
        WorkSessionStatus.COMPLETED
    )
    assert stack.currentWidget() is main_window.operations_page
    controller.handle_logout()


def test_logout_interrupts_an_active_local_work_session(qtbot) -> None:
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
    )
    _login_window, _session_context, controller = _setup_controller(
        qtbot,
        OperationService(MockOperationProvider((operation,))),
    )
    controller.handle_face_authentication(
        OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    )
    main_window = controller.main_window
    assert main_window is not None
    qtbot.addWidget(main_window)
    main_window.show_safety_verification(operation)
    controller.handle_operation_start_authorized(
        OperationStartAuthorization(
            operation_id=41,
            verified_ppe_ids=(1,),
            sample_count=8,
            window_size=8,
            authorized_at=datetime.now(UTC),
        )
    )

    controller.handle_logout()

    assert controller.work_session_service.current is None
    assert controller.work_session_service.last_finished.status is (
        WorkSessionStatus.INTERRUPTED
    )
