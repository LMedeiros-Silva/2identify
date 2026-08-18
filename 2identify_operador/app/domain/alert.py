"""Immutable local safety violation and alert contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class SafetyViolationType(StrEnum):
    """Violation categories understood by the local safety pipeline."""

    PPE_ABSENT = "ppe_absent"
    PERSON_IN_RISK_AREA = "person_in_risk_area"
    MONITORING_INTERRUPTED = "monitoring_interrupted"


class SafetyAlertSeverity(StrEnum):
    """Operational importance independent from UI color or transport."""

    WARNING = "warning"
    CRITICAL = "critical"


class SafetyAlertStatus(StrEnum):
    """Lifecycle of one deduplicated local alert."""

    ACTIVE = "active"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class SafetyViolation:
    """One currently observed rule violation before debounce and cooldown."""

    violation_type: SafetyViolationType
    subject_key: str
    summary: str
    severity: SafetyAlertSeverity
    ppe_id: int | None = None
    ppe_name: str | None = None
    track_id: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.violation_type, SafetyViolationType):
            raise ValueError("violation_type deve ser um SafetyViolationType")
        if not isinstance(self.severity, SafetyAlertSeverity):
            raise ValueError("severity deve ser um SafetyAlertSeverity")
        subject_key = self.subject_key.strip().casefold()
        summary = self.summary.strip()
        if not subject_key or not summary:
            raise ValueError("subject_key e summary não podem ser vazios")
        if self.ppe_id is not None and self.ppe_id <= 0:
            raise ValueError("ppe_id deve ser positivo quando informado")
        ppe_name = self.ppe_name
        if ppe_name is not None:
            ppe_name = ppe_name.strip()
            if not ppe_name:
                raise ValueError("ppe_name não pode ser vazio")
        if self.track_id is not None and self.track_id <= 0:
            raise ValueError("track_id deve ser positivo quando informado")
        if self.violation_type is SafetyViolationType.PPE_ABSENT and (
            self.ppe_id is None or ppe_name is None
        ):
            raise ValueError("uma violação PPE_ABSENT exige ppe_id e ppe_name")
        object.__setattr__(self, "subject_key", subject_key)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "ppe_name", ppe_name)

    @property
    def deduplication_key(self) -> str:
        return f"{self.violation_type.value}:{self.subject_key}"


@dataclass(frozen=True, slots=True)
class SafetyAlert:
    """One local alert bound to the WorkSession that observed the violation."""

    alert_id: UUID
    work_session_id: UUID
    operator_id: int
    operation_id: int
    camera_id: int | None
    risk_area_id: int | None
    violation: SafetyViolation
    first_observed_at: datetime
    raised_at: datetime
    resolved_at: datetime | None
    status: SafetyAlertStatus

    def __post_init__(self) -> None:
        if not isinstance(self.alert_id, UUID) or not isinstance(
            self.work_session_id,
            UUID,
        ):
            raise ValueError("alert_id e work_session_id devem ser UUID")
        if self.operator_id <= 0 or self.operation_id <= 0:
            raise ValueError("operador e operação devem possuir ids positivos")
        if self.camera_id is not None and self.camera_id <= 0:
            raise ValueError("camera_id deve ser positivo quando informado")
        if self.risk_area_id is not None and self.risk_area_id <= 0:
            raise ValueError("risk_area_id deve ser positivo quando informado")
        if not isinstance(self.violation, SafetyViolation):
            raise ValueError("violation deve ser uma SafetyViolation")
        if not isinstance(self.status, SafetyAlertStatus):
            raise ValueError("status deve ser um SafetyAlertStatus")

        first_observed_at = _as_utc(self.first_observed_at, "first_observed_at")
        raised_at = _as_utc(self.raised_at, "raised_at")
        resolved_at = self.resolved_at
        if raised_at < first_observed_at:
            raise ValueError("raised_at não pode anteceder first_observed_at")
        if self.status is SafetyAlertStatus.ACTIVE:
            if resolved_at is not None:
                raise ValueError("alerta ativo não pode possuir resolved_at")
        else:
            if resolved_at is None:
                raise ValueError("alerta resolvido exige resolved_at")
            resolved_at = _as_utc(resolved_at, "resolved_at")
            if resolved_at < raised_at:
                raise ValueError("resolved_at não pode anteceder raised_at")
        object.__setattr__(self, "first_observed_at", first_observed_at)
        object.__setattr__(self, "raised_at", raised_at)
        object.__setattr__(self, "resolved_at", resolved_at)

    def resolve(self, resolved_at: datetime) -> SafetyAlert:
        """Return a resolved snapshot while preserving the same alert identity."""

        if self.status is not SafetyAlertStatus.ACTIVE:
            raise ValueError("somente um alerta ativo pode ser resolvido")
        return replace(
            self,
            resolved_at=resolved_at,
            status=SafetyAlertStatus.RESOLVED,
        )


def _as_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} deve possuir fuso horário")
    return value.astimezone(UTC)
