from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.domain import (
    SafetyAlertSeverity,
    SafetyAlertStatus,
    SafetyViolation,
    SafetyViolationType,
    WorkSession,
    WorkSessionStatus,
)
from app.engine import AlertEngine

_STARTED_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_ALERT_IDS = (
    UUID("11111111-1111-1111-1111-111111111111"),
    UUID("22222222-2222-2222-2222-222222222222"),
)
_WORK_SESSION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _work_session(
    session_id: UUID = _WORK_SESSION_ID,
) -> WorkSession:
    return WorkSession(
        session_id=session_id,
        operator_id=15,
        operation_id=41,
        camera_id=None,
        risk_area_id=7,
        verified_ppe_ids=(4,),
        safety_verified_at=_STARTED_AT - timedelta(seconds=1),
        ppe_sample_count=8,
        ppe_window_size=8,
        started_at=_STARTED_AT,
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
    )


def _violation(ppe_id: int = 4, name: str = "Mangote") -> SafetyViolation:
    return SafetyViolation(
        SafetyViolationType.PPE_ABSENT,
        f"ppe:{ppe_id}",
        f"{name} obrigatório ausente",
        SafetyAlertSeverity.CRITICAL,
        ppe_id=ppe_id,
        ppe_name=name,
    )


def _engine(
    *,
    minimum_observations: int = 3,
    persistence_seconds: float = 2,
    resolution_observations: int = 2,
    cooldown_seconds: float = 10,
) -> AlertEngine:
    identifiers = iter(_ALERT_IDS)
    return AlertEngine(
        minimum_consecutive_observations=minimum_observations,
        minimum_persistence_seconds=persistence_seconds,
        resolution_consecutive_observations=resolution_observations,
        cooldown_seconds=cooldown_seconds,
        alert_id_factory=lambda: next(identifiers),
    )


def test_alert_engine_debounces_and_deduplicates_persistent_violation() -> None:
    engine = _engine()
    session = _work_session()
    violation = _violation()

    first = engine.observe(session, (violation,), _STARTED_AT)
    second = engine.observe(
        session,
        (violation,),
        _STARTED_AT + timedelta(seconds=1),
    )
    raised = engine.observe(
        session,
        (violation,),
        _STARTED_AT + timedelta(seconds=2),
    )
    repeated = engine.observe(
        session,
        (violation,),
        _STARTED_AT + timedelta(seconds=3),
    )

    assert first.raised_alerts == ()
    assert second.raised_alerts == ()
    assert len(raised.raised_alerts) == 1
    assert raised.raised_alerts[0].alert_id == _ALERT_IDS[0]
    assert repeated.raised_alerts == ()
    assert repeated.active_alerts == raised.raised_alerts


def test_alert_engine_resolves_after_stable_recovery() -> None:
    engine = _engine(minimum_observations=1, persistence_seconds=0)
    session = _work_session()
    violation = _violation()
    raised = engine.observe(session, (violation,), _STARTED_AT)

    pending = engine.observe(session, (), _STARTED_AT + timedelta(seconds=1))
    resolved = engine.observe(session, (), _STARTED_AT + timedelta(seconds=2))

    assert len(raised.raised_alerts) == 1
    assert pending.active_alerts == raised.raised_alerts
    assert len(resolved.resolved_alerts) == 1
    assert resolved.resolved_alerts[0].status is SafetyAlertStatus.RESOLVED
    assert resolved.resolved_alerts[0].alert_id == _ALERT_IDS[0]
    assert resolved.active_alerts == ()


def test_alert_engine_applies_cooldown_to_recurrent_condition() -> None:
    engine = _engine(
        minimum_observations=1,
        persistence_seconds=0,
        resolution_observations=1,
        cooldown_seconds=10,
    )
    session = _work_session()
    violation = _violation()
    engine.observe(session, (violation,), _STARTED_AT)
    engine.observe(session, (), _STARTED_AT + timedelta(seconds=1))

    blocked = engine.observe(
        session,
        (violation,),
        _STARTED_AT + timedelta(seconds=2),
    )
    allowed = engine.observe(
        session,
        (violation,),
        _STARTED_AT + timedelta(seconds=11),
    )

    assert blocked.raised_alerts == ()
    assert len(allowed.raised_alerts) == 1
    assert allowed.raised_alerts[0].alert_id == _ALERT_IDS[1]


def test_alert_engine_treats_distinct_ppe_as_distinct_conditions() -> None:
    engine = _engine(minimum_observations=1, persistence_seconds=0)

    update = engine.observe(
        _work_session(),
        (_violation(), _violation(2, "Capacete")),
        _STARTED_AT,
    )

    assert len(update.raised_alerts) == 2
    assert {item.violation.ppe_id for item in update.active_alerts} == {2, 4}


def test_alert_engine_requires_reset_before_another_work_session() -> None:
    engine = _engine(minimum_observations=1, persistence_seconds=0)
    engine.observe(_work_session(), (_violation(),), _STARTED_AT)

    with pytest.raises(ValueError, match="resetar"):
        engine.observe(
            _work_session(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
            (),
            _STARTED_AT + timedelta(seconds=1),
        )

    engine.reset()
    update = engine.observe(
        _work_session(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        (),
        _STARTED_AT + timedelta(seconds=1),
    )
    assert update.active_alerts == ()
