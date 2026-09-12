"""Administrative projection of one live Operator work session."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ActiveOperationOverallStatus(StrEnum):
    COMPLIANT = "compliant"
    ATTENTION = "attention"
    NON_COMPLIANT = "non_compliant"


class ActiveOperationPpe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ppe_id: Annotated[int, Field(gt=0)]
    name: Annotated[str, Field(min_length=1, max_length=150)]
    state: Literal["collecting", "confirmed", "absent", "unstable", "unmapped"]

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name não pode ser vazio")
        return normalized


class ActiveOperationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    work_session_id: UUID
    session_status: Literal["active", "ended"]
    operator_id: Annotated[int, Field(gt=0)]
    operator_name: Annotated[str, Field(min_length=1, max_length=150)]
    operation_id: Annotated[int, Field(gt=0)]
    operation_name: Annotated[str, Field(min_length=1, max_length=150)]
    started_at: datetime
    observed_at: datetime
    camera_id: Annotated[int, Field(gt=0)] | None = None
    camera_name: Annotated[str, Field(min_length=1, max_length=150)] | None = None
    ppe: Annotated[tuple[ActiveOperationPpe, ...], Field(max_length=100)]
    overall_status: ActiveOperationOverallStatus

    @field_validator("operator_name", "operation_name", "camera_name")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("texto não pode ser vazio")
        return normalized

    @field_validator("started_at", "observed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp deve possuir fuso horário")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ActiveOperationSnapshot:
        if self.started_at > self.observed_at:
            raise ValueError("started_at não pode ocorrer depois de observed_at")
        if (self.camera_id is None) != (self.camera_name is None):
            raise ValueError("camera_id e camera_name devem ser informados juntos")
        identifiers = tuple(item.ppe_id for item in self.ppe)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("ppe não pode repetir identificadores")
        return self


__all__ = [
    "ActiveOperationOverallStatus",
    "ActiveOperationPpe",
    "ActiveOperationSnapshot",
]
