from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.domain.ppe_management import ActiveOperationSnapshot

RealtimeAlertLevel = Literal["warning", "critical"]
RealtimeAlertStatus = Literal["nao_lido", "lido", "encerrado"]
RealtimeAlertCategory = Literal[
    "ppe",
    "ergonomics",
    "monitoring",
    "risk_area",
    "safety",
]


@dataclass(frozen=True, slots=True)
class ConnectionReadyEvent:
    event_id: UUID
    occurred_at: datetime
    status: Literal["ready", "awaiting_alert_ingestion"]


@dataclass(frozen=True, slots=True)
class HeartbeatEvent:
    event_id: UUID
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class RealtimeAlert:
    event_id: UUID
    occurred_at: datetime
    alert_id: int
    occurrence_id: int
    level: RealtimeAlertLevel
    status: RealtimeAlertStatus
    summary: str
    detected_at: datetime
    camera_id: int | None
    category: RealtimeAlertCategory = "safety"


@dataclass(frozen=True, slots=True)
class PpeSessionUpdatedEvent:
    event_id: UUID
    occurred_at: datetime
    snapshot: ActiveOperationSnapshot


RealtimeEvent = ConnectionReadyEvent | HeartbeatEvent | RealtimeAlert | PpeSessionUpdatedEvent


__all__ = [
    "ConnectionReadyEvent",
    "HeartbeatEvent",
    "PpeSessionUpdatedEvent",
    "RealtimeAlert",
    "RealtimeAlertCategory",
    "RealtimeAlertLevel",
    "RealtimeAlertStatus",
    "RealtimeEvent",
]
