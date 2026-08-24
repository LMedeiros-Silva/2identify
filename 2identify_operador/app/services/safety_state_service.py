"""Typed snapshots sent from local monitoring to the API safety aggregator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.domain import (
    SafetyAlert,
    SafetyAlertSeverity,
    SafetyAlertStatus,
    SafetyViolationType,
    WorkSession,
)


class SafetyStateLevel(StrEnum):
    MEDIUM = "medium"
    CRITICAL = "critical"


class SafetyStateReason(StrEnum):
    PPE_MISSING = "PPE_MISSING"
    ERGONOMIC_RISK = "ERGONOMIC_RISK"
    PERSON_IN_RISK_AREA = "PERSON_IN_RISK_AREA"


class HardwareSafetyState(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


_REASON_BY_VIOLATION = {
    SafetyViolationType.PPE_ABSENT: SafetyStateReason.PPE_MISSING,
    SafetyViolationType.ERGONOMIC_RISK: SafetyStateReason.ERGONOMIC_RISK,
    SafetyViolationType.PERSON_IN_RISK_AREA: SafetyStateReason.PERSON_IN_RISK_AREA,
}


@dataclass(frozen=True, slots=True)
class SafetyConditionState:
    condition_id: str
    reason: SafetyStateReason
    level: SafetyStateLevel
    first_observed_at: datetime

    def __post_init__(self) -> None:
        identifier = self.condition_id.strip().casefold()
        if not identifier:
            raise ValueError("condition_id não pode ser vazio")
        if not isinstance(self.reason, SafetyStateReason):
            raise ValueError("reason deve ser SafetyStateReason")
        if not isinstance(self.level, SafetyStateLevel):
            raise ValueError("level deve ser SafetyStateLevel")
        observed = _as_utc(self.first_observed_at)
        object.__setattr__(self, "condition_id", identifier)
        object.__setattr__(self, "first_observed_at", observed)


@dataclass(frozen=True, slots=True)
class SafetyStateSnapshot:
    work_session_id: UUID
    operation_id: int
    camera_id: int | None
    observed_at: datetime
    conditions: tuple[SafetyConditionState, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.work_session_id, UUID):
            raise ValueError("work_session_id deve ser UUID")
        if self.operation_id <= 0:
            raise ValueError("operation_id deve ser positivo")
        if self.camera_id is not None and self.camera_id <= 0:
            raise ValueError("camera_id deve ser positivo quando informado")
        conditions = tuple(self.conditions)
        if len({item.condition_id for item in conditions}) != len(conditions):
            raise ValueError("conditions não pode conter duplicidades")
        observed_at = _as_utc(self.observed_at)
        if any(item.first_observed_at > observed_at for item in conditions):
            raise ValueError("condição não pode começar depois do snapshot")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "conditions", conditions)

    @classmethod
    def from_alerts(
        cls,
        work_session: WorkSession,
        alerts: tuple[SafetyAlert, ...],
        observed_at: datetime,
    ) -> SafetyStateSnapshot:
        conditions: list[SafetyConditionState] = []
        for alert in alerts:
            if alert.status is not SafetyAlertStatus.ACTIVE:
                raise ValueError("snapshot aceita somente alertas ativos")
            reason = _REASON_BY_VIOLATION.get(alert.violation.violation_type)
            if reason is None:
                continue
            level = (
                SafetyStateLevel.CRITICAL
                if alert.violation.severity is SafetyAlertSeverity.CRITICAL
                else SafetyStateLevel.MEDIUM
            )
            conditions.append(
                SafetyConditionState(
                    condition_id=alert.violation.deduplication_key,
                    reason=reason,
                    level=level,
                    first_observed_at=alert.first_observed_at,
                )
            )
        return cls(
            work_session_id=work_session.session_id,
            operation_id=work_session.operation_id,
            camera_id=work_session.camera_id,
            observed_at=observed_at,
            conditions=tuple(sorted(conditions, key=lambda item: item.condition_id)),
        )


@dataclass(frozen=True, slots=True)
class SafetyStateDeliveryReceipt:
    state: HardwareSafetyState
    reason: SafetyStateReason | None
    active_conditions: int


class SafetyStateDeliveryError(RuntimeError):
    pass


class SafetyStateDeliveryUnavailableError(SafetyStateDeliveryError):
    pass


class SafetyStateDeliveryRejectedError(SafetyStateDeliveryError):
    pass


class SafetyStateSender(Protocol):
    def send_safety_state(
        self,
        snapshot: SafetyStateSnapshot,
        access_token: str,
    ) -> SafetyStateDeliveryReceipt: ...


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp deve possuir fuso horário")
    return value.astimezone(UTC)


__all__ = [
    "HardwareSafetyState",
    "SafetyConditionState",
    "SafetyStateDeliveryError",
    "SafetyStateDeliveryReceipt",
    "SafetyStateDeliveryRejectedError",
    "SafetyStateDeliveryUnavailableError",
    "SafetyStateLevel",
    "SafetyStateReason",
    "SafetyStateSender",
    "SafetyStateSnapshot",
]
