"""Immutable administrative projection of the Operator's PPE observations."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class PpeLiveState(StrEnum):
    COLLECTING = "collecting"
    CONFIRMED = "confirmed"
    ABSENT = "absent"
    UNSTABLE = "unstable"
    UNMAPPED = "unmapped"


class WorkSessionLiveStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class ActiveOperationOverallStatus(StrEnum):
    COMPLIANT = "compliant"
    ATTENTION = "attention"
    NON_COMPLIANT = "non_compliant"


@dataclass(frozen=True, slots=True)
class PpeLiveItem:
    ppe_id: int
    name: str
    state: PpeLiveState


@dataclass(frozen=True, slots=True)
class ActiveOperationSnapshot:
    work_session_id: UUID
    session_status: WorkSessionLiveStatus
    operator_id: int
    operator_name: str
    operation_id: int
    operation_name: str
    started_at: datetime
    observed_at: datetime
    camera_id: int | None
    camera_name: str | None
    ppe: tuple[PpeLiveItem, ...]
    overall_status: ActiveOperationOverallStatus
