"""Validated ingestion contracts for alerts emitted by Operator clients."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.realtime import normalize_public_summary

SafetyViolationName = Literal[
    "ppe_absent",
    "person_in_risk_area",
    "monitoring_interrupted",
    "ergonomic_risk",
]


class OperatorAlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    work_session_id: UUID
    operation_id: Annotated[int, Field(gt=0)]
    camera_id: Annotated[int, Field(gt=0)] | None = None
    risk_area_id: Annotated[int, Field(gt=0)] | None = None
    violation_type: SafetyViolationName
    subject_key: Annotated[str, Field(min_length=1, max_length=150)]
    summary: Annotated[str, Field(min_length=1, max_length=500)]
    severity: Literal["warning", "critical"]
    first_observed_at: AwareDatetime
    raised_at: AwareDatetime

    @field_validator("subject_key")
    @classmethod
    def normalize_subject_key(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if re.fullmatch(r"[a-z0-9:_-]+", normalized) is None:
            raise ValueError("subject_key possui formato inválido")
        return normalized

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        return normalize_public_summary(value)

    @field_validator("first_observed_at", "raised_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_timeline(self) -> OperatorAlertCreate:
        if self.raised_at < self.first_observed_at:
            raise ValueError("raised_at não pode anteceder first_observed_at")
        return self


class OperatorAlertReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: UUID
    alert_id: Annotated[int, Field(gt=0)]
    occurrence_id: Annotated[int, Field(gt=0)]
    duplicate: bool
