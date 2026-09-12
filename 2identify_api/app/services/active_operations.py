"""Process-local active-operation projection for the authenticated Admin stream."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.schemas.active_operations import (
    ActiveOperationOverallStatus,
    ActiveOperationPpe,
    ActiveOperationSnapshot,
)
from app.schemas.operations import OperationDetail
from app.schemas.realtime import RealtimeEventEnvelope
from app.schemas.safety_state import OperatorSafetyStateSnapshot

if TYPE_CHECKING:
    from app.realtime.broker import RealtimeEventBroker


class ActiveOperationSnapshotConflictError(RuntimeError):
    """Reported monitoring state does not match authoritative configuration."""


@dataclass(frozen=True, slots=True)
class ActiveOperationUpdateResult:
    snapshot: ActiveOperationSnapshot


class ActiveOperationRegistry:
    """Keep current snapshots and broadcast every liveness/update observation."""

    def __init__(self, broker: RealtimeEventBroker) -> None:
        self._broker = broker
        self._active: dict[tuple[int, object], ActiveOperationSnapshot] = {}
        self._lock = asyncio.Lock()

    async def list_active(self) -> tuple[ActiveOperationSnapshot, ...]:
        async with self._lock:
            return tuple(
                sorted(
                    self._active.values(),
                    key=lambda item: (item.started_at, item.operator_id),
                )
            )

    async def update(
        self,
        *,
        operator_id: int,
        operator_name: str,
        operation: OperationDetail,
        snapshot: OperatorSafetyStateSnapshot,
    ) -> ActiveOperationSnapshot:
        self._validate_configuration(operation, snapshot)
        key = (operator_id, snapshot.work_session_id)
        async with self._lock:
            previous = self._active.get(key)
            projected = self._project(
                operator_id=operator_id,
                operator_name=operator_name,
                operation=operation,
                source=snapshot,
                previous=previous,
            )
            if snapshot.session_status == "active":
                self._active[key] = projected
            else:
                self._active.pop(key, None)

        await self._broker.publish(
            RealtimeEventEnvelope(
                event_type="ppe.session.updated",
                payload=projected,
            )
        )
        return projected

    @staticmethod
    def _validate_configuration(
        operation: OperationDetail,
        snapshot: OperatorSafetyStateSnapshot,
    ) -> None:
        if operation.id != snapshot.operation_id or not operation.active:
            raise ActiveOperationSnapshotConflictError(
                "snapshot não pertence a uma operação ativa"
            )
        if operation.risk_area.camera_id != snapshot.camera_id:
            raise ActiveOperationSnapshotConflictError(
                "câmera do snapshot não corresponde à operação"
            )
        if snapshot.session_status == "ended":
            return
        required_ids = {item.id for item in operation.required_ppe}
        reported_ids = {item.ppe_id for item in snapshot.ppe}
        if required_ids != reported_ids:
            raise ActiveOperationSnapshotConflictError(
                "snapshot não cobre exatamente os EPIs obrigatórios"
            )

    @classmethod
    def _project(
        cls,
        *,
        operator_id: int,
        operator_name: str,
        operation: OperationDetail,
        source: OperatorSafetyStateSnapshot,
        previous: ActiveOperationSnapshot | None,
    ) -> ActiveOperationSnapshot:
        if source.started_at is None:
            raise ActiveOperationSnapshotConflictError(
                "snapshot de gestão exige started_at"
            )
        if source.session_status == "ended" and previous is not None:
            return previous.model_copy(
                update={
                    "session_status": "ended",
                    "observed_at": source.observed_at,
                }
            )
        state_by_id = {item.ppe_id: item.state for item in source.ppe}
        ppe = tuple(
            ActiveOperationPpe(
                ppe_id=item.id,
                name=item.name,
                state=state_by_id.get(item.id, "collecting"),
            )
            for item in operation.required_ppe
        )
        return ActiveOperationSnapshot(
            work_session_id=source.work_session_id,
            session_status=source.session_status,
            operator_id=operator_id,
            operator_name=operator_name,
            operation_id=operation.id,
            operation_name=operation.name,
            started_at=source.started_at,
            observed_at=source.observed_at,
            camera_id=operation.risk_area.camera_id,
            camera_name=operation.risk_area.camera_name,
            ppe=ppe,
            overall_status=cls._overall_status(ppe),
        )

    @staticmethod
    def _overall_status(
        ppe: tuple[ActiveOperationPpe, ...],
    ) -> ActiveOperationOverallStatus:
        states = {item.state for item in ppe}
        if states & {"absent", "unmapped"}:
            return ActiveOperationOverallStatus.NON_COMPLIANT
        if states == {"confirmed"}:
            return ActiveOperationOverallStatus.COMPLIANT
        return ActiveOperationOverallStatus.ATTENTION


__all__ = [
    "ActiveOperationRegistry",
    "ActiveOperationSnapshotConflictError",
    "ActiveOperationUpdateResult",
]
