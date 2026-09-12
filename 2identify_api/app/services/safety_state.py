"""Small realtime cache derived from the persisted active alert lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.realtime.broker import RealtimeEventBroker
from app.schemas.safety_state import (
    HardwareSafetyState,
    SafetyConditionReason,
    SafetyConditionSnapshot,
    SafetyStateMessage,
    safe_state_message,
)

Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)

_LEVEL_RANK = {"medium": 1, "critical": 2}
_STATE_FOR_LEVEL: dict[str, HardwareSafetyState] = {
    "medium": "YELLOW",
    "critical": "RED",
}
_REASON_PRIORITY: dict[SafetyConditionReason, int] = {
    "OTHER_SAFETY_ALERT": 0,
    "MONITORING_INTERRUPTED": 0,
    "ERGONOMIC_RISK": 1,
    "PPE_MISSING": 2,
    "PERSON_IN_RISK_AREA": 3,
}


@dataclass(frozen=True, slots=True)
class SafetyStateUpdateResult:
    message: SafetyStateMessage
    published: bool


class SafetyStateAggregator:
    """Serialize database reads and publish only effective changes, without polling."""

    def __init__(
        self,
        broker: RealtimeEventBroker,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._broker = broker
        self._clock = clock or _utc_now
        self._lock = asyncio.Lock()
        self._current: SafetyStateMessage | None = None

    async def current(self) -> SafetyStateMessage | None:
        async with self._lock:
            return self._current

    async def send_current(self, subscription_id: UUID) -> bool:
        """Queue a reconnect snapshot atomically with respect to state updates."""

        async with self._lock:
            if self._current is None:
                return False
            return await self._broker.send_to(subscription_id, self._current)

    async def refresh(
        self,
        read_active: Callable[[], tuple[SafetyConditionSnapshot, ...]],
    ) -> SafetyStateUpdateResult:
        """Read after commit, inside the lock, so concurrent mutations cannot regress state."""
        async with self._lock:
            try:
                conditions = await run_in_threadpool(read_active)
                candidate = self._calculate_message(conditions)
            except Exception:
                # Never keep advertising a cached GREEN after an authoritative read fails.
                self._current = None
                raise
            if self._current is not None and _same_effective_state(
                candidate,
                self._current,
            ):
                return SafetyStateUpdateResult(self._current, False)
            self._current = candidate
            try:
                await self._broker.publish(candidate)
            except Exception:
                self._current = None
                raise
            return SafetyStateUpdateResult(candidate, True)

    async def refresh_after_commit(
        self,
        read_active: Callable[[], tuple[SafetyConditionSnapshot, ...]],
    ) -> None:
        """A failed hardware cache must not undo an acknowledged alert/Admin event."""
        try:
            await self.refresh(read_active)
        except Exception as error:
            logger.error(
                "safety_tower_refresh_failed_after_commit",
                extra={"error_type": type(error).__name__},
            )

    def _calculate_message(
        self, conditions: tuple[SafetyConditionSnapshot, ...]
    ) -> SafetyStateMessage:
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
