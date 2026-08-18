from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.domain import (
    SafetyAlert,
    SafetyAlertSeverity,
    SafetyAlertStatus,
    SafetyViolation,
    SafetyViolationType,
)

_OBSERVED_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _violation() -> SafetyViolation:
    return SafetyViolation(
        SafetyViolationType.PPE_ABSENT,
        "ppe:4",
        "Mangote obrigatório ausente",
        SafetyAlertSeverity.CRITICAL,
        ppe_id=4,
        ppe_name="Mangote",
    )


def _alert() -> SafetyAlert:
    return SafetyAlert(
        alert_id=UUID("11111111-1111-1111-1111-111111111111"),
        work_session_id=UUID("22222222-2222-2222-2222-222222222222"),
        operator_id=15,
        operation_id=41,
        camera_id=None,
        risk_area_id=7,
        violation=_violation(),
        first_observed_at=_OBSERVED_AT,
        raised_at=_OBSERVED_AT + timedelta(seconds=1),
        resolved_at=None,
        status=SafetyAlertStatus.ACTIVE,
    )


def test_safety_violation_normalizes_stable_deduplication_key() -> None:
    violation = _violation()

    assert violation.deduplication_key == "ppe_absent:ppe:4"
    assert violation.ppe_name == "Mangote"


def test_ppe_absent_violation_requires_ppe_context() -> None:
    with pytest.raises(ValueError, match="exige ppe_id e ppe_name"):
        SafetyViolation(
            SafetyViolationType.PPE_ABSENT,
            "ppe:4",
            "Mangote ausente",
            SafetyAlertSeverity.CRITICAL,
        )


def test_active_alert_resolves_without_changing_identity() -> None:
    alert = _alert()
    resolved_at = _OBSERVED_AT + timedelta(seconds=5)

    resolved = alert.resolve(resolved_at)

    assert resolved.alert_id == alert.alert_id
    assert resolved.status is SafetyAlertStatus.RESOLVED
    assert resolved.resolved_at == resolved_at
    assert alert.status is SafetyAlertStatus.ACTIVE


def test_alert_rejects_inconsistent_lifecycle() -> None:
    alert = _alert()
    with pytest.raises(ValueError, match="ativo não pode"):
        SafetyAlert(
            alert_id=alert.alert_id,
            work_session_id=alert.work_session_id,
            operator_id=alert.operator_id,
            operation_id=alert.operation_id,
            camera_id=None,
            risk_area_id=None,
            violation=alert.violation,
            first_observed_at=alert.first_observed_at,
            raised_at=alert.raised_at,
            resolved_at=alert.raised_at,
            status=SafetyAlertStatus.ACTIVE,
        )
