"""Administrative alert detail and lifecycle contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

AdminAlertCategory = Literal[
    "ppe",
    "ergonomics",
    "monitoring",
    "risk_area",
    "safety",
]
AdminAlertLevel = Literal["warning", "critical"]
AdminAlertStatus = Literal["nao_lido", "lido", "encerrado"]


class AdminAlertActor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(gt=0)]
    name: Annotated[str, Field(min_length=1, max_length=150)]


class AdminAlertSector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(gt=0)]
    name: Annotated[str, Field(min_length=1, max_length=100)]


class AdminAlertEmployee(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(gt=0)]
    name: Annotated[str, Field(min_length=1, max_length=150)]
    registration: Annotated[str, Field(min_length=1, max_length=50)]
    role: str | None = Field(default=None, max_length=100)
    shift: str | None = Field(default=None, max_length=50)
    sector: AdminAlertSector | None = None


class AdminAlertCamera(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(gt=0)]
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: str | None = Field(default=None, max_length=255)
    sector: AdminAlertSector | None = None


class AdminAlertOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(gt=0)]
    type: Annotated[str, Field(min_length=1, max_length=100)]
    description: str | None = None
    confidence: float | None = Field(default=None, ge=0.0)
    image_reference: str | None = Field(default=None, max_length=500)
    video_reference: str | None = Field(default=None, max_length=500)
    detected_at: AwareDatetime
    employee: AdminAlertEmployee | None = None
    camera: AdminAlertCamera | None = None


class AdminAlertOperationalContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    work_session_id: UUID
    operation_id: Annotated[int, Field(gt=0)]
    operation_name: str | None = Field(default=None, max_length=150)
    risk_area_id: Annotated[int, Field(gt=0)] | None = None
    violation_type: Annotated[str, Field(min_length=1, max_length=50)]
    subject_key: Annotated[str, Field(min_length=1, max_length=150)]
    operator: AdminAlertActor | None = None
    received_at: AwareDatetime


class AdminAlertDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[int, Field(gt=0)]
    category: AdminAlertCategory
    level: AdminAlertLevel
    status: AdminAlertStatus
    summary: Annotated[str, Field(min_length=1)]
    observation: str | None = None
    created_at: AwareDatetime
    received_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    confirmed_by: AdminAlertActor | None = None
    closed_at: AwareDatetime | None = None
    closed_by: AdminAlertActor | None = None
    occurrence: AdminAlertOccurrence
    operational_context: AdminAlertOperationalContext | None = None


class AdminAlertList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[AdminAlertDetail, ...]
    total: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    offset: Annotated[int, Field(ge=0)]


class AdminAlertActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: str | None = Field(default=None, max_length=1_000)


def ensure_aware(value: datetime) -> datetime:
    """Keep PostgreSQL values and make SQLite test values explicitly UTC."""

    from datetime import UTC

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


__all__ = [
    "AdminAlertActionRequest",
    "AdminAlertActor",
    "AdminAlertCamera",
    "AdminAlertDetail",
    "AdminAlertEmployee",
    "AdminAlertList",
    "AdminAlertOccurrence",
    "AdminAlertOperationalContext",
    "AdminAlertSector",
    "ensure_aware",
]
