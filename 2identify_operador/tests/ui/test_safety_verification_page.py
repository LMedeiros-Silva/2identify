from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QLabel, QPushButton, QSplitter

from app.core.session import AuthenticationMethod, OperatorSession
from app.domain.operation import Operation, PpeRequirement, RiskAreaReference
from app.engine import (
    PpeSafetyEngine,
    PpeStabilityDecision,
    PpeStabilitySnapshot,
    PpeStabilityState,
)
from app.ui.components import CameraFrameView
from app.ui.safety import (
    PpeInferenceState,
    SafetyCameraState,
    SafetyVerificationPage,
)


def _session() -> OperatorSession:
    return OperatorSession(
        operator_id=15,
        operator_name="João Silva",
        login_time=datetime(2026, 8, 16, 13, 30, tzinfo=UTC),
        authentication_method=AuthenticationMethod.FACE_ID,
    )


def test_safety_page_presents_truthful_initial_verification_state(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    operation = Operation(
        operation_id=41,
        name="Inspeção de segurança",
        required_ppe=(
            PpeRequirement(1, "Capacete de segurança"),
            PpeRequirement(2, "Botas de segurança"),
        ),
        risk_area=RiskAreaReference(7, "Linha de Produção A"),
    )

    page.set_operation(operation)

    assert page.operation is operation
    assert page.findChild(QSplitter, "safetySplitter") is not None
    assert page.findChild(QLabel, "safetyOperationName").text() == operation.name
    assert page.findChild(QLabel, "safetyOperatorName").text() == "João Silva"
    assert page.findChild(QLabel, "safetyRiskAreaName").text() == (
        "Linha de Produção A"
    )
    assert page.findChild(QLabel, "safetyCameraStatus").text() == "NÃO INICIALIZADA"
    assert page.camera_state is SafetyCameraState.NOT_INITIALIZED
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "OPERAÇÃO NÃO LIBERADA"
    )
    assert page.findChild(QLabel, "safetyReleaseStatus").text() == (
        "AGUARDANDO VERIFICAÇÃO"
    )
    assert [
        label.text() for label in page.findChildren(QLabel, "safetyPpeName")
    ] == ["Capacete de segurança", "Botas de segurança"]
    assert {
        label.text() for label in page.findChildren(QLabel, "safetyPpeState")
    } == {"AGUARDANDO"}
    assert not page.findChild(QPushButton, "safetyStartOperationButton").isEnabled()


def test_safety_page_does_not_invent_missing_risk_area_or_ppe(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    page.show()

    page.set_operation(Operation(41, "Inspeção de segurança"))

    assert page.findChild(QLabel, "safetyRiskAreaName").text() == (
        "Área de risco não configurada"
    )
    assert page.findChild(QLabel, "safetyPpeCount").text() == "0 ITENS"
    assert page.findChild(QLabel, "safetyPpeEmptyState").isVisibleTo(page)
    assert page.findChildren(QLabel, "safetyPpeState") == []


def test_safety_page_emits_back_navigation_intent(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    back_button = page.findChild(QPushButton, "safetyBackButton")

    with qtbot.waitSignal(page.back_requested, timeout=1_000):
        qtbot.mouseClick(back_button, Qt.MouseButton.LeftButton)


def test_safety_page_emits_camera_lifecycle_intents(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    page.set_operation(Operation(41, "Inspeção de segurança"))

    with qtbot.waitSignal(page.camera_start_requested, timeout=1_000):
        page.activate()

    assert page.camera_state is SafetyCameraState.STARTING
    assert page.findChild(QLabel, "safetyCameraStatus").text() == "INICIALIZANDO"

    with qtbot.waitSignal(page.camera_stop_requested, timeout=1_000):
        page.deactivate()

    assert page.camera_state is SafetyCameraState.NOT_INITIALIZED


def test_safety_page_renders_owned_frame_without_changing_ppe_state(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    page.set_operation(
        Operation(
            41,
            "Inspeção de segurança",
            required_ppe=(PpeRequirement(1, "Capacete de segurança"),),
        )
    )
    page.activate()
    frame = QImage(160, 120, QImage.Format.Format_RGB888)
    frame.fill(QColor("#1677d2"))

    page.update_camera_frame(frame)

    preview = page.findChild(CameraFrameView, "safetyCameraPreview")
    assert preview.has_frame
    assert page.camera_state is SafetyCameraState.ACTIVE
    assert page.findChild(QLabel, "safetyPpeState").text() == "AGUARDANDO"
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "OPERAÇÃO NÃO LIBERADA"
    )


def test_safety_page_allows_retry_after_camera_failure(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    page.show()
    page.set_operation(Operation(41, "Inspeção de segurança"))
    page.activate()
    page.show_camera_failure("Câmera indisponível para teste.", unavailable=True)
    retry = page.findChild(QPushButton, "safetyCameraRetryButton")

    assert page.camera_state is SafetyCameraState.UNAVAILABLE
    assert retry.isVisibleTo(page)
    with qtbot.waitSignal(page.camera_start_requested, timeout=1_000):
        qtbot.mouseClick(retry, Qt.MouseButton.LeftButton)

    assert page.camera_state is SafetyCameraState.STARTING


def test_safety_page_presents_stable_ppe_decisions_without_releasing_work(
    qtbot,
) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(
            PpeRequirement(1, "Capacete de segurança", "capacete"),
            PpeRequirement(2, "Botas de segurança", "bota"),
        ),
    )
    page.set_operation(operation)
    page.activate()
    page.show_inference_ready(("bota", "capacete"))
    snapshot = PpeStabilitySnapshot(
        decisions=(
            PpeStabilityDecision(
                "capacete",
                PpeStabilityState.CONFIRMED_PRESENT,
                observed_frames=4,
                sample_count=5,
                presence_ratio=0.8,
            ),
            PpeStabilityDecision(
                "bota",
                PpeStabilityState.CONFIRMED_ABSENT,
                observed_frames=1,
                sample_count=5,
                presence_ratio=0.2,
            ),
        ),
        sample_count=5,
        window_size=8,
    )

    page.update_ppe_safety(
        PpeSafetyEngine().evaluate(operation, ("bota", "capacete"), snapshot)
    )

    states = page.findChildren(QLabel, "safetyPpeState")
    assert [label.text() for label in states] == ["CONFIRMADO", "AUSENTE"]
    assert [label.property("state") for label in states] == [
        "confirmed",
        "absent",
    ]
    assert page.inference_state is PpeInferenceState.ACTIVE
    assert page.findChild(QLabel, "safetyInferenceStatus").text() == (
        "IA ATIVA · 5/8 AMOSTRAS"
    )
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "OPERAÇÃO NÃO LIBERADA"
    )
    assert "EPI obrigatório ausente" in page.findChild(
        QLabel,
        "safetyReleaseDescription",
    ).text()
    assert not page.findChild(QPushButton, "safetyStartOperationButton").isEnabled()


def test_safety_page_enables_start_intent_only_for_compliant_assessment(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
    )
    page.set_operation(operation)
    page.activate()
    page.show_inference_ready(("capacete",))
    snapshot = PpeStabilitySnapshot(
        decisions=(
            PpeStabilityDecision(
                "capacete",
                PpeStabilityState.CONFIRMED_PRESENT,
                observed_frames=8,
                sample_count=8,
                presence_ratio=1.0,
            ),
        ),
        sample_count=8,
        window_size=8,
    )
    page.update_ppe_safety(
        PpeSafetyEngine().evaluate(operation, ("capacete",), snapshot)
    )

    assert page.findChild(QLabel, "safetyPpeState").text() == "CONFIRMADO"
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "VERIFICAÇÃO CONCLUÍDA"
    )
    assert page.findChild(QLabel, "safetyReleaseStatus").text() == (
        "EPIs CONFORMES"
    )
    start_button = page.findChild(QPushButton, "safetyStartOperationButton")
    assert start_button.isEnabled()
    with qtbot.waitSignal(page.operation_start_requested, timeout=1_000) as emitted:
        qtbot.mouseClick(start_button, Qt.MouseButton.LeftButton)
    assert emitted.args == [41]


def test_safety_page_revokes_start_when_evidence_regresses(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    operation = Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(PpeRequirement(1, "Capacete", "capacete"),),
    )
    page.set_operation(operation)
    page.activate()
    page.show_inference_ready(("capacete",))
    engine = PpeSafetyEngine()
    confirmed = PpeStabilitySnapshot(
        (
            PpeStabilityDecision(
                "capacete",
                PpeStabilityState.CONFIRMED_PRESENT,
                5,
                5,
                1.0,
            ),
        ),
        5,
        8,
    )
    absent = PpeStabilitySnapshot(
        (
            PpeStabilityDecision(
                "capacete",
                PpeStabilityState.CONFIRMED_ABSENT,
                0,
                5,
                0.0,
            ),
        ),
        5,
        8,
    )

    page.update_ppe_safety(engine.evaluate(operation, ("capacete",), confirmed))
    start_button = page.findChild(QPushButton, "safetyStartOperationButton")
    assert start_button.isEnabled()

    page.update_ppe_safety(engine.evaluate(operation, ("capacete",), absent))

    assert not start_button.isEnabled()
    assert page.findChild(QLabel, "safetyReleaseTitle").text() == (
        "OPERAÇÃO NÃO LIBERADA"
    )
    assert page.findChild(QLabel, "safetyReleaseStatus").text() == "EPI AUSENTE"


def test_safety_page_marks_required_ppe_without_model_mapping(qtbot) -> None:
    page = SafetyVerificationPage(_session())
    qtbot.addWidget(page)
    page.set_operation(
        Operation(
            41,
            "Inspeção de segurança",
            required_ppe=(PpeRequirement(1, "Proteção especial"),),
        )
    )
    page.activate()

    page.show_inference_ready(("capacete",))

    state = page.findChild(QLabel, "safetyPpeState")
    assert state.text() == "SEM MAPEAMENTO"
    assert state.property("state") == "unmapped"
