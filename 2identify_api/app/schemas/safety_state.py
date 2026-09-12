"""Operator snapshots and the compact safety message consumed by ESP32 devices."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

SafetyConditionLevel = Literal["medium", "critical"]
SafetyConditionReason = Literal[
    "PPE_MISSING",
    "ERGONOMIC_RISK",
    "PERSON_IN_RISK_AREA",
    "MONITORING_INTERRUPTED",
    "OTHER_SAFETY_ALERT",
]
HardwareSafetyState = Literal["GREEN", "YELLOW", "RED"]
PpeRequirementState = Literal[
    "collecting",
    "confirmed",
    "absent",
    "unstable",
    "unmapped",
]


class SafetyConditionSnapshot(BaseModel):
    """One debounced active condition reported by an authenticated Operator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: Annotated[str, Field(min_length=1, max_length=200)]
    reason: SafetyConditionReason
    level: SafetyConditionLevel
    first_observed_at: AwareDatetime

    @field_validator("condition_id")
    @classmethod
    def normalize_condition_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if re.fullmatch(r"[a-z0-9:_-]+", normalized) is None:
            raise ValueError("condition_id possui formato inválido")
        return normalized

    @field_validator("first_observed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class OperatorPpeStateSnapshot(BaseModel):
    """One required PPE state already calculated by the Operator pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ppe_id: Annotated[int, Field(gt=0)]
    state: PpeRequirementState


class OperatorSafetyStateSnapshot(BaseModel):
    """Complete current safety state for one local WorkSession."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    work_session_id: UUID
    operation_id: Annotated[int, Field(gt=0)]
    camera_id: Annotated[int, Field(gt=0)] | None = None
    observed_at: AwareDatetime
    started_at: AwareDatetime | None = None
    session_status: Literal["active", "ended"] = "active"
    ppe: Annotated[tuple[OperatorPpeStateSnapshot, ...], Field(max_length=100)] = ()
    conditions: Annotated[tuple[SafetyConditionSnapshot, ...], Field(max_length=100)] = ()

    @field_validator("observed_at", "started_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_snapshot(self) -> OperatorSafetyStateSnapshot:
        identifiers = tuple(item.condition_id for item in self.conditions)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("conditions não pode conter identificadores duplicados")
        ppe_ids = tuple(item.ppe_id for item in self.ppe)
        if len(set(ppe_ids)) != len(ppe_ids):
            raise ValueError("ppe não pode conter identificadores duplicados")
        if self.started_at is None and self.ppe:
            raise ValueError("ppe exige started_at")
        if self.started_at is not None and self.started_at > self.observed_at:
            raise ValueError("started_at não pode ocorrer depois de observed_at")
        if self.session_status == "ended" and self.started_at is None:
            raise ValueError("snapshot encerrado exige started_at")
        if self.session_status == "ended" and (self.ppe or self.conditions):
            raise ValueError("snapshot encerrado deve estar vazio")
        if any(
            item.first_observed_at > self.observed_at + timedelta(minutes=5)
            for item in self.conditions
        ):
            raise ValueError("condição não pode começar depois de observed_at")
        return self


class SafetyStateMessage(BaseModel):
    """Flat versioned message intentionally small enough for an ESP32."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["safety_state"] = "safety_state"
    schema_version: Literal[1] = 1
    state: HardwareSafetyState
    reason: SafetyConditionReason | None
    active_conditions: Annotated[int, Field(ge=0, le=10_000)]
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at deve possuir fuso horário")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_state_reason(self) -> SafetyStateMessage:
        if self.state == "GREEN":
            if self.reason is not None or self.active_conditions != 0:
                raise ValueError("GREEN não pode possuir condição ativa")
        elif self.reason is None or self.active_conditions == 0:
            raise ValueError("YELLOW e RED exigem condição ativa")
        return self

    def as_json_message(self) -> dict[str, object]:
        return cast(dict[str, object], self.model_dump(mode="json"))


def safe_state_message(at: datetime) -> SafetyStateMessage:
    return SafetyStateMessage(
        state="GREEN",
        reason=None,
        active_conditions=0,
        updated_at=at,
    )


__all__ = [
    "HardwareSafetyState",
    "OperatorPpeStateSnapshot",
    "OperatorSafetyStateSnapshot",
    "PpeRequirementState",
    "SafetyConditionLevel",
    "SafetyConditionReason",
    "SafetyConditionSnapshot",
    "SafetyStateMessage",
    "safe_state_message",
]
