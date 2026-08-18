"""Framework-independent authorization and industrial work-session concepts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class WorkSessionStatus(StrEnum):
    """Lifecycle states for one locally represented industrial operation."""

    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class OperationStartAuthorization:
    """One-shot PPE authorization emitted by the safety gate."""

    operation_id: int
    verified_ppe_ids: tuple[int, ...]
    sample_count: int
    window_size: int
    authorized_at: datetime

    def __post_init__(self) -> None:
        verified_ppe_ids = tuple(self.verified_ppe_ids)
        if self.operation_id <= 0:
            raise ValueError("operation_id deve ser maior que zero")
        if not verified_ppe_ids or any(item <= 0 for item in verified_ppe_ids):
            raise ValueError("verified_ppe_ids deve conter identificadores positivos")
        if len(set(verified_ppe_ids)) != len(verified_ppe_ids):
            raise ValueError("verified_ppe_ids não pode conter duplicidades")
        if self.window_size < 1 or not 1 <= self.sample_count <= self.window_size:
            raise ValueError("a amostragem deve estar dentro da janela")
        if self.authorized_at.tzinfo is None or self.authorized_at.utcoffset() is None:
            raise ValueError("authorized_at deve possuir fuso horário")
        object.__setattr__(self, "verified_ppe_ids", verified_ppe_ids)
        object.__setattr__(self, "authorized_at", self.authorized_at.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class WorkSession:
    """Immutable local snapshot of one operator executing one operation."""

    session_id: UUID
    operator_id: int
    operation_id: int
    camera_id: int | None
    risk_area_id: int | None
    verified_ppe_ids: tuple[int, ...]
    safety_verified_at: datetime
    ppe_sample_count: int
    ppe_window_size: int
    started_at: datetime
    finished_at: datetime | None
    status: WorkSessionStatus

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, UUID):
            raise ValueError("session_id deve ser UUID")
        if self.operator_id <= 0 or self.operation_id <= 0:
            raise ValueError("operador e operação devem possuir identificadores positivos")
        if self.camera_id is not None and self.camera_id <= 0:
            raise ValueError("camera_id deve ser positivo quando informado")
        if self.risk_area_id is not None and self.risk_area_id <= 0:
            raise ValueError("risk_area_id deve ser positivo quando informado")
        verified_ppe_ids = tuple(self.verified_ppe_ids)
        if not verified_ppe_ids or any(item <= 0 for item in verified_ppe_ids):
            raise ValueError("verified_ppe_ids deve conter identificadores positivos")
        if len(set(verified_ppe_ids)) != len(verified_ppe_ids):
            raise ValueError("verified_ppe_ids não pode conter duplicidades")
        if self.ppe_window_size < 1 or not 1 <= self.ppe_sample_count <= self.ppe_window_size:
            raise ValueError("a amostragem de EPI deve estar dentro da janela")
        if not isinstance(self.status, WorkSessionStatus):
            raise ValueError("status deve ser um WorkSessionStatus")

        safety_verified_at = _as_utc(self.safety_verified_at, "safety_verified_at")
        started_at = _as_utc(self.started_at, "started_at")
        finished_at = self.finished_at
        if safety_verified_at > started_at:
            raise ValueError("a verificação de segurança não pode ocorrer após o início")
        if self.status is WorkSessionStatus.ACTIVE:
            if finished_at is not None:
                raise ValueError("sessão ativa não pode possuir finished_at")
        else:
            if finished_at is None:
                raise ValueError("sessão encerrada deve possuir finished_at")
            finished_at = _as_utc(finished_at, "finished_at")
            if finished_at < started_at:
                raise ValueError("finished_at não pode ocorrer antes de started_at")

        object.__setattr__(self, "verified_ppe_ids", verified_ppe_ids)
        object.__setattr__(self, "safety_verified_at", safety_verified_at)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "finished_at", finished_at)

    @property
    def is_active(self) -> bool:
        return self.status is WorkSessionStatus.ACTIVE

    def finish(self, finished_at: datetime, status: WorkSessionStatus) -> WorkSession:
        """Return a closed snapshot without mutating the active one."""

        if not self.is_active:
            raise ValueError("somente uma sessão ativa pode ser encerrada")
        if status not in {
            WorkSessionStatus.COMPLETED,
            WorkSessionStatus.INTERRUPTED,
        }:
            raise ValueError("status final inválido")
        return replace(self, finished_at=finished_at, status=status)


def _as_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} deve possuir fuso horário")
    return value.astimezone(UTC)
