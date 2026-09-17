"""Typed snapshots sent from local monitoring to the API safety aggregator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.domain import (
    Operation,
    SafetyAlert,
    SafetyAlertSeverity,
    SafetyAlertStatus,
    SafetyViolationType,
    WorkSession,
)
from app.engine.ppe_safety import PpeRequirementSafetyState, PpeSafetyAssessment


class SafetyStateLevel(StrEnum):
    MEDIUM = "medium"
    CRITICAL = "critical"


class SafetyStateReason(StrEnum):
    PPE_MISSING = "PPE_MISSING"
    ERGONOMIC_RISK = "ERGONOMIC_RISK"
    PERSON_IN_RISK_AREA = "PERSON_IN_RISK_AREA"
    MONITORING_INTERRUPTED = "MONITORING_INTERRUPTED"
    OTHER_SAFETY_ALERT = "OTHER_SAFETY_ALERT"


class HardwareSafetyState(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class PpeLiveState(StrEnum):
    COLLECTING = "collecting"
    CONFIRMED = "confirmed"
    ABSENT = "absent"
    UNSTABLE = "unstable"
    UNMAPPED = "unmapped"


class WorkSessionSnapshotStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


@dataclass(frozen=True, slots=True)
class PpeLiveStateSnapshot:
    ppe_id: int
    state: PpeLiveState

    def __post_init__(self) -> None:
        if self.ppe_id <= 0:
            raise ValueError("ppe_id deve ser positivo")
        if not isinstance(self.state, PpeLiveState):
            raise ValueError("state deve ser PpeLiveState")


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
    started_at: datetime | None = None
    session_status: WorkSessionSnapshotStatus = WorkSessionSnapshotStatus.ACTIVE
    ppe: tuple[PpeLiveStateSnapshot, ...] = ()

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
        started_at = self.started_at
        if started_at is not None:
            started_at = _as_utc(started_at)
            if started_at > observed_at:
                raise ValueError("started_at não pode ocorrer depois de observed_at")
        if not isinstance(self.session_status, WorkSessionSnapshotStatus):
            raise ValueError("session_status deve ser WorkSessionSnapshotStatus")
        ppe = tuple(self.ppe)
        if any(not isinstance(item, PpeLiveStateSnapshot) for item in ppe):
            raise ValueError("ppe deve conter PpeLiveStateSnapshot")
        if len({item.ppe_id for item in ppe}) != len(ppe):
            raise ValueError("ppe não pode conter duplicidades")
        if ppe and started_at is None:
            raise ValueError("estados de EPI exigem started_at")
        if self.session_status is WorkSessionSnapshotStatus.ENDED:
            if started_at is None:
                raise ValueError("snapshot encerrado exige started_at")
            if conditions or ppe:
                raise ValueError("snapshot encerrado deve estar vazio")
        if any(item.first_observed_at > observed_at for item in conditions):
            raise ValueError("condição não pode começar depois do snapshot")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "ppe", ppe)

    @classmethod
    def from_alerts(
        cls,
        work_session: WorkSession,
        alerts: tuple[SafetyAlert, ...],
        observed_at: datetime,
        *,
        ppe_assessment: PpeSafetyAssessment | None = None,
        operation: Operation | None = None,
    ) -> SafetyStateSnapshot:
        if (
            ppe_assessment is not None
            and ppe_assessment.camera_id is not None
            and ppe_assessment.camera_id != work_session.camera_id
        ):
            raise ValueError("evidência PPE não pertence à câmera primária")
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
        if operation is not None and operation.operation_id != work_session.operation_id:
            raise ValueError("operação não corresponde à WorkSession")
        fallback_ppe = (
            tuple(
                PpeLiveStateSnapshot(
                    item.ppe_id,
                    PpeLiveState.COLLECTING
                    if item.detection_class is not None else PpeLiveState.UNMAPPED,
                )
                for item in operation.required_ppe
            )
            if operation is not None and ppe_assessment is None else ()
        )
        return cls(
            work_session_id=work_session.session_id,
            operation_id=work_session.operation_id,
            camera_id=work_session.camera_id,
            observed_at=observed_at,
            conditions=tuple(sorted(conditions, key=lambda item: item.condition_id)),
            started_at=(
                work_session.started_at
                if ppe_assessment is not None or operation is not None else None
            ),
            ppe=(
                tuple(
                    PpeLiveStateSnapshot(
                        item.ppe_id,
                        _PPE_LIVE_STATE_BY_ASSESSMENT[item.state],
                    )
                    for item in ppe_assessment.requirements
                )
                if ppe_assessment is not None
                else fallback_ppe
            ),
        )

    @classmethod
    def initial(
        cls,
        work_session: WorkSession,
        operation: Operation,
        observed_at: datetime,
    ) -> SafetyStateSnapshot:
        return cls(
            work_session_id=work_session.session_id,
            operation_id=work_session.operation_id,
            camera_id=work_session.camera_id,
            observed_at=observed_at,
            conditions=(),
            started_at=work_session.started_at,
            ppe=tuple(
                PpeLiveStateSnapshot(
                    item.ppe_id,
                    (
                        PpeLiveState.COLLECTING
                        if item.detection_class is not None
                        else PpeLiveState.UNMAPPED
                    ),
                )
                for item in operation.required_ppe
            ),
        )

    @classmethod
    def ended(
        cls,
        work_session: WorkSession,
        observed_at: datetime,
    ) -> SafetyStateSnapshot:
        return cls(
            work_session_id=work_session.session_id,
            operation_id=work_session.operation_id,
            camera_id=work_session.camera_id,
            observed_at=observed_at,
            conditions=(),
            started_at=work_session.started_at,
            session_status=WorkSessionSnapshotStatus.ENDED,
            ppe=(),
        )


@dataclass(frozen=True, slots=True)
class SafetyStateDeliveryReceipt:
    state: HardwareSafetyState
    reason: SafetyStateReason | None
    active_conditions: int


_PPE_LIVE_STATE_BY_ASSESSMENT = {
    PpeRequirementSafetyState.COLLECTING: PpeLiveState.COLLECTING,
    PpeRequirementSafetyState.CONFIRMED: PpeLiveState.CONFIRMED,
    PpeRequirementSafetyState.ABSENT: PpeLiveState.ABSENT,
    PpeRequirementSafetyState.UNSTABLE: PpeLiveState.UNSTABLE,
    PpeRequirementSafetyState.UNMAPPED: PpeLiveState.UNMAPPED,
}


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
    "PpeLiveState",
    "PpeLiveStateSnapshot",
    "SafetyConditionState",
    "SafetyStateDeliveryError",
    "SafetyStateDeliveryReceipt",
    "SafetyStateDeliveryRejectedError",
    "SafetyStateDeliveryUnavailableError",
    "SafetyStateLevel",
    "SafetyStateReason",
    "SafetyStateSender",
    "SafetyStateSnapshot",
    "WorkSessionSnapshotStatus",
]
