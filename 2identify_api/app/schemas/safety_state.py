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
]
HardwareSafetyState = Literal["GREEN", "YELLOW", "RED"]


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


class OperatorSafetyStateSnapshot(BaseModel):
    """Complete current safety state for one local WorkSession."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    work_session_id: UUID
    operation_id: Annotated[int, Field(gt=0)]
    camera_id: Annotated[int, Field(gt=0)] | None = None
    observed_at: AwareDatetime
    conditions: Annotated[tuple[SafetyConditionSnapshot, ...], Field(max_length=100)] = ()

    @field_validator("observed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_snapshot(self) -> OperatorSafetyStateSnapshot:
        identifiers = tuple(item.condition_id for item in self.conditions)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("conditions não pode conter identificadores duplicados")
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
    "OperatorSafetyStateSnapshot",
    "SafetyConditionLevel",
    "SafetyConditionReason",
    "SafetyConditionSnapshot",
    "SafetyStateMessage",
    "safe_state_message",
]
