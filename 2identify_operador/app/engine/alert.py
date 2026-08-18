"""Stateful debounce, deduplication and cooldown for local safety alerts."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.domain.alert import (
    SafetyAlert,
    SafetyAlertStatus,
    SafetyViolation,
)
from app.domain.work_session import WorkSession

AlertIdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class AlertEngineUpdate:
    """Immutable changes and active state produced by one observation cycle."""

    raised_alerts: tuple[SafetyAlert, ...]
    resolved_alerts: tuple[SafetyAlert, ...]
    active_alerts: tuple[SafetyAlert, ...]

    def __post_init__(self) -> None:
        all_alerts = (*self.raised_alerts, *self.resolved_alerts, *self.active_alerts)
        if any(not isinstance(item, SafetyAlert) for item in all_alerts):
            raise ValueError("a atualização deve conter somente SafetyAlert")
        if any(
            item.status is not SafetyAlertStatus.ACTIVE
            for item in (*self.raised_alerts, *self.active_alerts)
        ):
            raise ValueError("alertas levantados e ativos devem possuir status ACTIVE")
        if any(
            item.status is not SafetyAlertStatus.RESOLVED
            for item in self.resolved_alerts
        ):
            raise ValueError("alertas resolvidos devem possuir status RESOLVED")


@dataclass(slots=True)
class _ConditionState:
    violation: SafetyViolation
    first_observed_at: datetime | None = None
    consecutive_observations: int = 0
    consecutive_clear_observations: int = 0
    active_alert: SafetyAlert | None = None
    next_raise_allowed_at: datetime | None = None


class AlertEngine:
    """Emit one alert per persistent condition and resolve it after stable recovery."""

    def __init__(
        self,
        *,
        minimum_consecutive_observations: int,
        minimum_persistence_seconds: float,
        resolution_consecutive_observations: int,
        cooldown_seconds: float,
        alert_id_factory: AlertIdFactory = uuid4,
    ) -> None:
        if minimum_consecutive_observations < 1:
            raise ValueError("minimum_consecutive_observations deve ser positivo")
        if minimum_persistence_seconds < 0:
            raise ValueError("minimum_persistence_seconds não pode ser negativo")
        if resolution_consecutive_observations < 1:
            raise ValueError("resolution_consecutive_observations deve ser positivo")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds não pode ser negativo")
        self._minimum_consecutive_observations = minimum_consecutive_observations
        self._minimum_persistence = timedelta(
            seconds=minimum_persistence_seconds
        )
        self._resolution_consecutive_observations = (
            resolution_consecutive_observations
        )
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._alert_id_factory = alert_id_factory
        self._states: dict[str, _ConditionState] = {}
        self._work_session_id: UUID | None = None
        self._last_observed_at: datetime | None = None

    @property
    def active_alerts(self) -> tuple[SafetyAlert, ...]:
        return self._active_alerts()

    def reset(self) -> None:
        """Discard all local state when the WorkSession lifecycle ends."""

        self._states.clear()
        self._work_session_id = None
        self._last_observed_at = None

    def observe(
        self,
        work_session: WorkSession,
        violations: Iterable[SafetyViolation],
        observed_at: datetime,
    ) -> AlertEngineUpdate:
        """Process the complete current violation set for one WorkSession."""

        if not isinstance(work_session, WorkSession) or not work_session.is_active:
            raise ValueError("AlertEngine exige uma WorkSession ativa")
        observed_at = _as_utc(observed_at)
        if observed_at < work_session.started_at:
            raise ValueError("observed_at não pode anteceder a WorkSession")
        if self._last_observed_at is not None and observed_at < self._last_observed_at:
            raise ValueError("observed_at não pode retroceder")
        if self._work_session_id is None:
            self._work_session_id = work_session.session_id
        elif self._work_session_id != work_session.session_id:
            raise ValueError("troque a WorkSession somente após resetar o AlertEngine")
        self._last_observed_at = observed_at

        current = self._normalize_violations(violations)
        raised: list[SafetyAlert] = []
        resolved: list[SafetyAlert] = []

        for key, violation in current.items():
            state = self._states.get(key)
            if state is None:
                state = _ConditionState(violation=violation)
                self._states[key] = state
            state.violation = violation
            state.consecutive_clear_observations = 0
            if state.first_observed_at is None:
                state.first_observed_at = observed_at
                state.consecutive_observations = 1
            else:
                state.consecutive_observations += 1
            if state.active_alert is None and self._can_raise(state, observed_at):
                alert = self._raise_alert(work_session, state, observed_at)
                state.active_alert = alert
                raised.append(alert)

        for key, state in self._states.items():
            if key in current:
                continue
            state.consecutive_observations = 0
            state.first_observed_at = None
            active_alert = state.active_alert
            if active_alert is None:
                state.consecutive_clear_observations = 0
                continue
            state.consecutive_clear_observations += 1
            if (
                state.consecutive_clear_observations
                < self._resolution_consecutive_observations
            ):
                continue
            resolved_alert = active_alert.resolve(observed_at)
            state.active_alert = None
            state.consecutive_clear_observations = 0
            state.next_raise_allowed_at = observed_at + self._cooldown
            resolved.append(resolved_alert)

        return AlertEngineUpdate(
            raised_alerts=tuple(raised),
            resolved_alerts=tuple(resolved),
            active_alerts=self._active_alerts(),
        )

    @staticmethod
    def _normalize_violations(
        violations: Iterable[SafetyViolation],
    ) -> dict[str, SafetyViolation]:
        result: dict[str, SafetyViolation] = {}
        for violation in violations:
            if not isinstance(violation, SafetyViolation):
                raise ValueError("violations deve conter somente SafetyViolation")
            key = violation.deduplication_key
            if key in result:
                raise ValueError(f"violação duplicada no mesmo ciclo: {key}")
            result[key] = violation
        return result

    def _can_raise(
        self,
        state: _ConditionState,
        observed_at: datetime,
    ) -> bool:
        first_observed_at = state.first_observed_at
        if first_observed_at is None:
            return False
        next_allowed = state.next_raise_allowed_at
        return (
            state.consecutive_observations
            >= self._minimum_consecutive_observations
            and observed_at - first_observed_at >= self._minimum_persistence
            and (next_allowed is None or observed_at >= next_allowed)
        )

    def _raise_alert(
        self,
        work_session: WorkSession,
        state: _ConditionState,
        raised_at: datetime,
    ) -> SafetyAlert:
        first_observed_at = state.first_observed_at
        if first_observed_at is None:
            raise RuntimeError("estado persistente sem first_observed_at")
        return SafetyAlert(
            alert_id=self._alert_id_factory(),
            work_session_id=work_session.session_id,
            operator_id=work_session.operator_id,
            operation_id=work_session.operation_id,
            camera_id=work_session.camera_id,
            risk_area_id=work_session.risk_area_id,
            violation=state.violation,
            first_observed_at=first_observed_at,
            raised_at=raised_at,
            resolved_at=None,
            status=SafetyAlertStatus.ACTIVE,
        )

    def _active_alerts(self) -> tuple[SafetyAlert, ...]:
        return tuple(
            sorted(
                (
                    state.active_alert
                    for state in self._states.values()
                    if state.active_alert is not None
                ),
                key=lambda alert: (alert.raised_at, str(alert.alert_id)),
            )
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at deve possuir fuso horário")
    return value.astimezone(UTC)
