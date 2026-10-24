"""Poll the database for alert changes and fan them out to public listeners.

Polling keeps this process independent from the authenticated API: new alerts,
Admin confirmations and closures, and resolved conditions all surface the same
way, and a listener that reconnects simply receives a fresh snapshot.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from starlette.concurrency import run_in_threadpool

from app.public_panel.repository import PublicAlert

logger = logging.getLogger(__name__)

Loader = Callable[[], list[PublicAlert]]


class FeedCapacityError(RuntimeError):
    """Raised when the panel already serves its maximum number of listeners."""


@dataclass(frozen=True, slots=True)
class FeedEvent:
    kind: str
    data: dict[str, object]


@dataclass(eq=False)
class FeedListener:
    queue: asyncio.Queue[FeedEvent | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=64)
    )


class PublicAlertFeed:
    def __init__(self, load: Loader, *, interval_seconds: float, max_listeners: int) -> None:
        self._load = load
        self._interval = interval_seconds
        self._max_listeners = max_listeners
        self._listeners: set[FeedListener] = set()
        self._alerts: list[PublicAlert] = []
        self._source_online = False
        self._loaded = False
        self._task: asyncio.Task[None] | None = None

    @property
    def listener_count(self) -> int:
        return len(self._listeners)

    def snapshot(self) -> dict[str, object]:
        return {
            "alerts": [alert.as_json() for alert in self._alerts],
            "source_online": self._source_online,
            "server_time": _now(),
        }

    async def start(self) -> None:
        await self.poll_once()
        self._task = asyncio.create_task(self._run(), name="public-alert-feed")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        for listener in list(self._listeners):
            self._close(listener)

    def subscribe(self) -> FeedListener:
        if len(self._listeners) >= self._max_listeners:
            raise FeedCapacityError("limite de espectadores atingido")
        listener = FeedListener()
        self._listeners.add(listener)
        return listener

    def unsubscribe(self, listener: FeedListener) -> None:
        self._listeners.discard(listener)

    async def poll_once(self) -> None:
        try:
            alerts = await run_in_threadpool(self._load)
        except Exception as error:  # database down, network, schema drift
            logger.warning(
                "public_panel_poll_failed", extra={"error_type": type(error).__name__}
            )
            self._set_online(False)
            return
        previous = {alert.id: alert for alert in self._alerts}
        current = {alert.id for alert in alerts}
        changed = [alert for alert in alerts if previous.get(alert.id) != alert]
        # Deleted rows and rows pushed out of the window leave the panel too.
        removed = sorted(alert_id for alert_id in previous if alert_id not in current)
        self._alerts = alerts
        self._set_online(True)
        if (changed or removed) and self._loaded:
            # Oldest first, so listeners apply changes in chronological order.
            payload = [alert.as_json() for alert in reversed(changed)]
            self._broadcast(FeedEvent("alerts", {"alerts": payload, "removed": removed}))
        self._loaded = True

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.poll_once()

    def _set_online(self, online: bool) -> None:
        if online != self._source_online:
            self._source_online = online
            self._broadcast(FeedEvent("status", {"source_online": online}))

    def _broadcast(self, event: FeedEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener.queue.put_nowait(event)
            except asyncio.QueueFull:
                # A stalled phone reconnects and receives a full snapshot instead.
                self._close(listener)

    def _close(self, listener: FeedListener) -> None:
        self._listeners.discard(listener)
        while not listener.queue.empty():
            listener.queue.get_nowait()
        listener.queue.put_nowait(None)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
