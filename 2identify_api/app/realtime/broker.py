"""Process-local, testable realtime event fan-out."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from fastapi import WebSocket

from app.schemas.realtime import RealtimeEventEnvelope

logger = logging.getLogger(__name__)


def _consume_finished_task(task: asyncio.Task[None]) -> None:
    """Consume a detached cleanup task result without leaking task warnings."""

    if task.cancelled():
        return
    try:
        task.exception()
    except asyncio.CancelledError:
        return


class BrokerClosedError(RuntimeError):
    """Raised when a subscriber is attached after application shutdown began."""


class BrokerCapacityError(RuntimeError):
    """Raised when a global or per-owner connection limit is reached."""


@runtime_checkable
class RealtimeEventSink(Protocol):
    """One serialized destination independent from FastAPI routing."""

    async def send(self, event: RealtimeEventEnvelope) -> None: ...

    async def close(self, *, code: int, reason: str) -> None: ...


@dataclass(frozen=True, slots=True)
class DeliveryReport:
    attempted: int
    enqueued: int
    disconnected: int


@dataclass(frozen=True, slots=True)
class _Subscriber:
    sink: RealtimeEventSink
    queue: asyncio.Queue[RealtimeEventEnvelope]
    writer_task: asyncio.Task[None]
    owner_id: int | None


@runtime_checkable
class RealtimeEventBroker(Protocol):
    """Internal publish/subscribe boundary for future committed alert events."""

    async def subscribe(
        self,
        sink: RealtimeEventSink,
        *,
        owner_id: int | None = None,
    ) -> UUID: ...

    async def unsubscribe(self, subscription_id: UUID) -> None: ...

    async def disconnect(
        self,
        subscription_id: UUID,
        *,
        code: int,
        reason: str,
    ) -> None: ...

    async def send_to(
        self,
        subscription_id: UUID,
        event: RealtimeEventEnvelope,
    ) -> bool: ...

    async def publish(self, event: RealtimeEventEnvelope) -> DeliveryReport: ...

    async def close(self, *, code: int, reason: str) -> None: ...


class WebSocketEventSink:
    """Serialize all writers targeting the same WebSocket connection."""

    def __init__(
        self,
        websocket: WebSocket,
        *,
        close_timeout_seconds: float = 2.0,
    ) -> None:
        if close_timeout_seconds <= 0:
            raise ValueError("close_timeout_seconds deve ser positivo")
        self._websocket = websocket
        self._close_timeout_seconds = close_timeout_seconds
        self._send_lock = asyncio.Lock()
        self._closed = False

    async def send(self, event: RealtimeEventEnvelope) -> None:
        async with self._send_lock:
            if self._closed:
                raise RuntimeError("conexão WebSocket encerrada")
            await self._websocket.send_json(event.as_json_message())

    async def close(self, *, code: int, reason: str) -> None:
        async with self._send_lock:
            if self._closed:
                return
            self._closed = True
            close_task = asyncio.create_task(
                self._websocket.close(code=code, reason=reason)
            )
            try:
                done, _pending = await asyncio.wait(
                    {close_task},
                    timeout=self._close_timeout_seconds,
                )
                if not done:
                    close_task.cancel()
                    close_task.add_done_callback(_consume_finished_task)
                    logger.warning("realtime_websocket_close_timed_out")
                    return
                close_task.result()
            except RuntimeError:
                # Starlette raises when the peer has already completed the close handshake.
                return


class InMemoryRealtimeEventBroker:
    """Fan out events inside one API process without persistence or replay guarantees."""

    def __init__(
        self,
        *,
        queue_capacity: int = 64,
        max_connections: int = 128,
        max_connections_per_owner: int = 4,
        sink_close_timeout_seconds: float = 2.0,
    ) -> None:
        if queue_capacity <= 0:
            raise ValueError("queue_capacity deve ser positivo")
        if max_connections <= 0:
            raise ValueError("max_connections deve ser positivo")
        if max_connections_per_owner <= 0:
            raise ValueError("max_connections_per_owner deve ser positivo")
        if max_connections_per_owner > max_connections:
            raise ValueError("limite por proprietário não pode exceder o limite global")
        if sink_close_timeout_seconds <= 0:
            raise ValueError("sink_close_timeout_seconds deve ser positivo")
        self._queue_capacity = queue_capacity
        self._max_connections = max_connections
        self._max_connections_per_owner = max_connections_per_owner
        self._sink_close_timeout_seconds = sink_close_timeout_seconds
        self._subscribers: dict[UUID, _Subscriber] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def subscribe(
        self,
        sink: RealtimeEventSink,
        *,
        owner_id: int | None = None,
    ) -> UUID:
        if owner_id is not None and owner_id <= 0:
            raise ValueError("owner_id deve ser positivo")
        subscription_id = uuid4()
        queue: asyncio.Queue[RealtimeEventEnvelope] = asyncio.Queue(
            maxsize=self._queue_capacity
        )
        async with self._lock:
            if self._closed:
                raise BrokerClosedError("broker em encerramento")
            if len(self._subscribers) >= self._max_connections:
                raise BrokerCapacityError("capacidade global de conexões atingida")
            owner_connections = sum(
                subscriber.owner_id == owner_id
                for subscriber in self._subscribers.values()
            )
            if (
                owner_id is not None
                and owner_connections >= self._max_connections_per_owner
            ):
                raise BrokerCapacityError("capacidade de conexões da conta atingida")
            writer_task = asyncio.create_task(
                self._writer_loop(subscription_id, sink, queue),
                name=f"realtime-writer-{subscription_id}",
            )
            self._subscribers[subscription_id] = _Subscriber(
                sink=sink,
                queue=queue,
                writer_task=writer_task,
                owner_id=owner_id,
            )
        logger.info("realtime_subscriber_connected")
        return subscription_id

    async def unsubscribe(self, subscription_id: UUID) -> None:
        await self.disconnect(
            subscription_id,
            code=1000,
            reason="Conexão encerrada",
        )

    async def disconnect(
        self,
        subscription_id: UUID,
        *,
        code: int,
        reason: str,
    ) -> None:
        async with self._lock:
            removed = self._subscribers.pop(subscription_id, None)
        if removed is not None:
            await self._shutdown_subscriber(removed, code=code, reason=reason)
            logger.info("realtime_subscriber_disconnected")

    async def send_to(
        self,
        subscription_id: UUID,
        event: RealtimeEventEnvelope,
    ) -> bool:
        slow_subscriber = None
        async with self._lock:
            subscriber = self._subscribers.get(subscription_id)
            if subscriber is None:
                return False
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                slow_subscriber = self._subscribers.pop(subscription_id)

        if slow_subscriber is not None:
            logger.warning("realtime_slow_subscriber_disconnected")
            await self._shutdown_subscriber(
                slow_subscriber,
                code=1013,
                reason="Cliente não acompanha o fluxo",
            )
            return False
        return True

    async def publish(self, event: RealtimeEventEnvelope) -> DeliveryReport:
        async with self._lock:
            subscription_ids = tuple(self._subscribers)

        results = await asyncio.gather(
            *(self.send_to(subscription_id, event) for subscription_id in subscription_ids),
        )
        attempted = len(subscription_ids)
        enqueued = sum(results)
        return DeliveryReport(
            attempted=attempted,
            enqueued=enqueued,
            disconnected=attempted - enqueued,
        )

    async def close(self, *, code: int, reason: str) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            subscribers = tuple(self._subscribers.values())
            self._subscribers.clear()

        await asyncio.gather(
            *(
                self._shutdown_subscriber(subscriber, code=code, reason=reason)
                for subscriber in subscribers
            ),
        )

    async def _writer_loop(
        self,
        subscription_id: UUID,
        sink: RealtimeEventSink,
        queue: asyncio.Queue[RealtimeEventEnvelope],
    ) -> None:
        try:
            while True:
                event = await queue.get()
                try:
                    await sink.send(event)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning(
                "realtime_event_delivery_failed",
                extra={"error_type": type(error).__name__},
            )
            await self._remove_failed_writer(subscription_id, sink)

    async def _remove_failed_writer(
        self,
        subscription_id: UUID,
        sink: RealtimeEventSink,
    ) -> None:
        async with self._lock:
            subscriber = self._subscribers.get(subscription_id)
            if subscriber is None or subscriber.sink is not sink:
                return
            self._subscribers.pop(subscription_id)
        await self._close_sink(
            sink,
            code=1011,
            reason="Entrega em tempo real indisponível",
        )

    async def _shutdown_subscriber(
        self,
        subscriber: _Subscriber,
        *,
        code: int,
        reason: str,
    ) -> None:
        subscriber.writer_task.cancel()
        done, _pending = await asyncio.wait(
            {subscriber.writer_task},
            timeout=self._sink_close_timeout_seconds,
        )
        if not done:
            subscriber.writer_task.add_done_callback(_consume_finished_task)
            logger.warning("realtime_writer_cancel_timed_out")
        else:
            await asyncio.gather(subscriber.writer_task, return_exceptions=True)
        await self._close_sink(subscriber.sink, code=code, reason=reason)

    async def _close_sink(
        self,
        sink: RealtimeEventSink,
        *,
        code: int,
        reason: str,
    ) -> None:
        close_task = asyncio.create_task(sink.close(code=code, reason=reason))
        try:
            done, _pending = await asyncio.wait(
                {close_task},
                timeout=self._sink_close_timeout_seconds,
            )
            if not done:
                close_task.cancel()
                close_task.add_done_callback(_consume_finished_task)
                logger.warning("realtime_subscriber_close_timed_out")
                return
            close_task.result()
        except Exception as error:
            logger.warning(
                "realtime_subscriber_close_failed",
                extra={"error_type": type(error).__name__},
            )
