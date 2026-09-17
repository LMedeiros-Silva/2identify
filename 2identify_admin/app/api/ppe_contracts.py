"""Shared HTTP/WebSocket validation for the API's active-operation projection."""

from datetime import UTC
from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    TypeAdapter,
    model_validator,
)

from app.domain.ppe_management import (
    ActiveOperationOverallStatus,
    ActiveOperationSnapshot,
    PpeLiveItem,
    PpeLiveState,
    WorkSessionLiveStatus,
)

_Name = Annotated[str, Field(min_length=1, max_length=150, pattern=r"\S")]


class PpeItemDto(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    ppe_id: PositiveInt
    name: _Name
    state: PpeLiveState


class ActiveOperationSnapshotDto(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    work_session_id: UUID
    session_status: WorkSessionLiveStatus
    operator_id: PositiveInt
    operator_name: _Name
    operation_id: PositiveInt
    operation_name: _Name
    started_at: AwareDatetime
    observed_at: AwareDatetime
    camera_id: PositiveInt | None = None
    camera_name: _Name | None = None
    ppe: Annotated[tuple[PpeItemDto, ...], Field(max_length=100)]
    overall_status: ActiveOperationOverallStatus

    @model_validator(mode="after")
    def validate_snapshot(self) -> "ActiveOperationSnapshotDto":
        if self.started_at > self.observed_at:
            raise ValueError("started_at não pode ocorrer depois de observed_at")
        if (self.camera_id is None) != (self.camera_name is None):
            raise ValueError("camera_id e camera_name devem ser informados juntos")
        if len({item.ppe_id for item in self.ppe}) != len(self.ppe):
            raise ValueError("ppe não pode repetir identificadores")
        return self

    def to_domain(self) -> ActiveOperationSnapshot:
        return ActiveOperationSnapshot(
            work_session_id=self.work_session_id,
            session_status=self.session_status,
            operator_id=self.operator_id,
            operator_name=self.operator_name,
            operation_id=self.operation_id,
            operation_name=self.operation_name,
            started_at=self.started_at.astimezone(UTC),
            observed_at=self.observed_at.astimezone(UTC),
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            ppe=tuple(PpeLiveItem(item.ppe_id, item.name, item.state) for item in self.ppe),
            overall_status=self.overall_status,
        )


_SNAPSHOTS = TypeAdapter(tuple[ActiveOperationSnapshotDto, ...])


def parse_active_operations(raw: bytes) -> tuple[ActiveOperationSnapshot, ...]:
    snapshots = _SNAPSHOTS.validate_json(raw, strict=True)
    keys = {(item.operator_id, item.work_session_id) for item in snapshots}
    if len(keys) != len(snapshots):
        raise ValueError("snapshot contém sessões duplicadas")
    if any(item.session_status is not WorkSessionLiveStatus.ACTIVE for item in snapshots):
        raise ValueError("snapshot inicial contém sessão encerrada")
    return tuple(item.to_domain() for item in snapshots)
