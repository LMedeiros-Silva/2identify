"""Immutable alert details displayed by the administrative workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

AlertCategory = Literal["ppe", "ergonomics", "monitoring", "risk_area", "safety"]
AlertLevel = Literal["warning", "critical"]
AlertStatus = Literal["nao_lido", "lido", "encerrado"]


@dataclass(frozen=True, slots=True)
class AlertActor:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class AlertSector:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class AlertEmployee:
    id: int
    name: str
    registration: str
    role: str | None
    shift: str | None
    sector: AlertSector | None


@dataclass(frozen=True, slots=True)
class AlertCamera:
    id: int
    name: str
    description: str | None
    sector: AlertSector | None


@dataclass(frozen=True, slots=True)
class AlertOccurrence:
    id: int
    type: str
    description: str | None
    confidence: float | None
    image_reference: str | None
    video_reference: str | None
    detected_at: datetime
    employee: AlertEmployee | None
    camera: AlertCamera | None


@dataclass(frozen=True, slots=True)
class AlertOperationalContext:
    event_id: UUID
    work_session_id: UUID
    operation_id: int
    risk_area_id: int | None
    violation_type: str
    subject_key: str
    operator: AlertActor | None
    received_at: datetime


@dataclass(frozen=True, slots=True)
class AdminAlert:
    id: int
    category: AlertCategory
    level: AlertLevel
    status: AlertStatus
    summary: str
    observation: str | None
    created_at: datetime
    received_at: datetime | None
    confirmed_at: datetime | None
    confirmed_by: AlertActor | None
    closed_at: datetime | None
    closed_by: AlertActor | None
    occurrence: AlertOccurrence
    operational_context: AlertOperationalContext | None


@dataclass(frozen=True, slots=True)
class AdminAlertPage:
    items: tuple[AdminAlert, ...]
    total: int
    limit: int
    offset: int


__all__ = [
    "AdminAlert",
    "AdminAlertPage",
    "AlertActor",
    "AlertCamera",
    "AlertCategory",
    "AlertEmployee",
    "AlertLevel",
    "AlertOccurrence",
    "AlertOperationalContext",
    "AlertSector",
    "AlertStatus",
]
