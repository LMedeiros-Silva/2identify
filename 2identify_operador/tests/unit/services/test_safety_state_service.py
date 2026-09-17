from datetime import UTC, datetime
from uuid import UUID

from app.domain import (
    Operation,
    PpeRequirement,
    SafetyAlert,
    SafetyAlertSeverity,
    SafetyAlertStatus,
    SafetyViolation,
    SafetyViolationType,
    WorkSession,
    WorkSessionStatus,
)
from app.engine import PpeRequirementSafetyState, PpeSafetyAssessment, PpeSafetyStatus
from app.engine.ppe_safety import PpeRequirementAssessment
from app.services.safety_state_service import (
    PpeLiveState,
    SafetyStateLevel,
    SafetyStateReason,
    SafetyStateSnapshot,
)

_OBSERVED_AT = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)


def _work_session() -> WorkSession:
    return WorkSession(
        session_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        operator_id=15,
        operation_id=41,
        camera_id=3,
        risk_area_id=7,
        verified_ppe_ids=(4,),
        safety_verified_at=_OBSERVED_AT,
        ppe_sample_count=8,
        ppe_window_size=8,
        started_at=_OBSERVED_AT,
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
    )


def _alert(identifier: int, violation: SafetyViolation) -> SafetyAlert:
    session = _work_session()
    return SafetyAlert(
        alert_id=UUID(f"{identifier:08d}-0000-4000-8000-000000000000"),
        work_session_id=session.session_id,
        operator_id=session.operator_id,
        operation_id=session.operation_id,
        camera_id=session.camera_id,
        risk_area_id=session.risk_area_id,
        violation=violation,
        first_observed_at=_OBSERVED_AT,
        raised_at=_OBSERVED_AT,
        resolved_at=None,
        status=SafetyAlertStatus.ACTIVE,
    )


def test_snapshot_maps_the_three_required_conditions_and_ignores_monitoring_faults() -> None:
    alerts = (
        _alert(
            1,
            SafetyViolation(
                SafetyViolationType.PPE_ABSENT,
                "ppe:4",
                "EPI obrigatório ausente",
                SafetyAlertSeverity.WARNING,
                ppe_id=4,
                ppe_name="Mangote",
            ),
        ),
        _alert(
            2,
            SafetyViolation(
                SafetyViolationType.ERGONOMIC_RISK,
                "ergonomics:trunk",
                "Postura ergonômica inadequada",
                SafetyAlertSeverity.CRITICAL,
            ),
        ),
        _alert(
            3,
            SafetyViolation(
                SafetyViolationType.PERSON_IN_RISK_AREA,
                "risk_area:7",
                "Pessoa dentro da área de risco",
                SafetyAlertSeverity.WARNING,
            ),
        ),
        _alert(
            4,
            SafetyViolation(
                SafetyViolationType.MONITORING_INTERRUPTED,
                "camera:3",
                "Monitoramento interrompido",
                SafetyAlertSeverity.CRITICAL,
            ),
        ),
    )

    snapshot = SafetyStateSnapshot.from_alerts(
        _work_session(),
        alerts,
        _OBSERVED_AT,
    )

    assert {(item.reason, item.level) for item in snapshot.conditions} == {
        (SafetyStateReason.PPE_MISSING, SafetyStateLevel.MEDIUM),
        (SafetyStateReason.ERGONOMIC_RISK, SafetyStateLevel.CRITICAL),
        (SafetyStateReason.PERSON_IN_RISK_AREA, SafetyStateLevel.MEDIUM),
    }


def test_monitoring_snapshot_carries_existing_ppe_assessment_and_lifecycle() -> None:
    assessment = PpeSafetyAssessment(
        operation_id=41,
        operation_active=True,
        status=PpeSafetyStatus.BLOCKED,
        requirements=(
            PpeRequirementAssessment(
                ppe_id=4,
                name="Mangote",
                detection_class="mangote",
                state=PpeRequirementSafetyState.ABSENT,
            ),
        ),
        sample_count=8,
        window_size=8,
    )
    active = SafetyStateSnapshot.from_alerts(
        _work_session(),
        (),
        _OBSERVED_AT,
        ppe_assessment=assessment,
    )
    assert active.started_at == _OBSERVED_AT
    assert active.session_status.value == "active"
    assert active.ppe[0].ppe_id == 4
    assert active.ppe[0].state is PpeLiveState.ABSENT

    initial = SafetyStateSnapshot.initial(
        _work_session(),
        Operation(
            41,
            "Inspeção",
            required_ppe=(PpeRequirement(4, "Mangote", "mangote"),),
        ),
        _OBSERVED_AT,
    )
    assert initial.ppe[0].state is PpeLiveState.COLLECTING

    ended = SafetyStateSnapshot.ended(_work_session(), _OBSERVED_AT)
    assert ended.session_status.value == "ended"
    assert ended.ppe == ()
    assert ended.conditions == ()
