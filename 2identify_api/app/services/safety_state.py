"""Process-local aggregation of Operator safety snapshots for signal hardware."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.realtime.broker import RealtimeEventBroker
from app.schemas.safety_state import (
    HardwareSafetyState,
    OperatorSafetyStateSnapshot,
    SafetyConditionReason,
    SafetyConditionSnapshot,
    SafetyStateMessage,
    safe_state_message,
)

Clock = Callable[[], datetime]

_LEVEL_RANK = {"medium": 1, "critical": 2}
_STATE_FOR_LEVEL: dict[str, HardwareSafetyState] = {
    "medium": "YELLOW",
    "critical": "RED",
}
_REASON_PRIORITY: dict[SafetyConditionReason, int] = {
    "ERGONOMIC_RISK": 1,
    "PPE_MISSING": 2,
    "PERSON_IN_RISK_AREA": 3,
}


@dataclass(frozen=True, slots=True)
class SafetyStateUpdateResult:
    message: SafetyStateMessage
    published: bool


class SafetyStateAggregator:
    """Merge complete per-session snapshots and publish only effective changes."""

    def __init__(
        self,
        broker: RealtimeEventBroker,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._broker = broker
        self._clock = clock or _utc_now
        self._sources: dict[tuple[int, UUID], tuple[SafetyConditionSnapshot, ...]] = {}
        self._lock = asyncio.Lock()
        self._current: SafetyStateMessage | None = None

    async def current(self) -> SafetyStateMessage | None:
        async with self._lock:
            return self._current

    async def send_current(self, subscription_id: UUID) -> bool:
        """Queue a reconnect snapshot atomically with respect to state updates."""

        async with self._lock:
            if self._current is None:
                return True
            return await self._broker.send_to(subscription_id, self._current)

    async def update(
        self,
        *,
        operator_id: int,
        snapshot: OperatorSafetyStateSnapshot,
    ) -> SafetyStateUpdateResult:
        if operator_id <= 0:
            raise ValueError("operator_id deve ser positivo")
        source_key = (operator_id, snapshot.work_session_id)
        async with self._lock:
            if snapshot.conditions:
                self._sources[source_key] = snapshot.conditions
            else:
                self._sources.pop(source_key, None)
            candidate = self._calculate_message()
            if self._current is not None and _same_effective_state(
                candidate,
                self._current,
            ):
                return SafetyStateUpdateResult(self._current, False)
            self._current = candidate
            await self._broker.publish(candidate)
            return SafetyStateUpdateResult(candidate, True)

    def _calculate_message(self) -> SafetyStateMessage:
        conditions = tuple(
            condition
            for source_conditions in self._sources.values()
            for condition in source_conditions
        )
        now = _as_utc(self._clock())
        if not conditions:
            return safe_state_message(now)
        highest_level = max(
            (item.level for item in conditions),
            key=_LEVEL_RANK.__getitem__,
        )
        leading = max(
            (item for item in conditions if item.level == highest_level),
            key=lambda item: (_REASON_PRIORITY[item.reason], item.condition_id),
        )
        return SafetyStateMessage(
            state=_STATE_FOR_LEVEL[highest_level],
            reason=leading.reason,
            active_conditions=len(conditions),
            updated_at=now,
        )


def _same_effective_state(
    first: SafetyStateMessage,
    second: SafetyStateMessage,
) -> bool:
    return (
        first.state,
        first.reason,
        first.active_conditions,
    ) == (
        second.state,
        second.reason,
        second.active_conditions,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock deve retornar datetime com fuso horário")
    return value.astimezone(UTC)


__all__ = ["SafetyStateAggregator", "SafetyStateUpdateResult"]
