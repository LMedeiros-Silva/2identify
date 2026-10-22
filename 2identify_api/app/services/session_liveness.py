"""Which Operator WorkSessions are still reporting, measured on the API clock."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from uuid import UUID

# (session owner, WorkSession): the owner is an account id or a Face ID employee key.
SessionKey = tuple[Hashable, UUID]

# Ended sessions are remembered so that a late alert retry cannot revive them.
_ENDED_MEMORY = 4_096


class SessionLiveness:
    """Process-local liveness of Operator WorkSessions.

    The Operator sends a safety snapshot every few seconds while a WorkSession is
    monitored. A persisted physical condition only drives the device tower while its
    session keeps reporting: rows left behind by a session that crashed, lost power or
    belongs to an earlier API process are history, not a current hazard. The rows are
    not modified, so a session that reconnects is counted again on its next report.
    """

    def __init__(
        self,
        ttl_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds deve ser positivo")
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._last_seen: dict[SessionKey, float] = {}
        self._ended: OrderedDict[SessionKey, None] = OrderedDict()

    def touch(self, operator_id: Hashable, work_session_id: UUID) -> bool:
        """Record a report; True when the session was not live a moment ago."""

        key = (operator_id, work_session_id)
        now = self._clock()
        with self._lock:
            if key in self._ended:
                return False
            previous = self._last_seen.get(key)
            self._last_seen[key] = now
            return previous is None or now - previous > self._ttl

    def end(self, operator_id: Hashable, work_session_id: UUID) -> bool:
        """Forget an ended session for good; True when it was being tracked."""

        key = (operator_id, work_session_id)
        with self._lock:
            self._ended[key] = None
            self._ended.move_to_end(key)
            while len(self._ended) > _ENDED_MEMORY:
                self._ended.popitem(last=False)
            return self._last_seen.pop(key, None) is not None

    def live_sessions(self) -> frozenset[SessionKey]:
        now = self._clock()
        with self._lock:
            return frozenset(
                key for key, seen in self._last_seen.items() if now - seen <= self._ttl
            )

    def prune_expired(self) -> bool:
        """Drop sessions past the TTL; True when any stopped reporting since the last call."""

        now = self._clock()
        with self._lock:
            expired = [key for key, seen in self._last_seen.items() if now - seen > self._ttl]
            for key in expired:
                del self._last_seen[key]
            return bool(expired)


__all__ = ["SessionKey", "SessionLiveness"]
