"""Bounded, fair latest-frame mailbox shared by inference workers."""

from __future__ import annotations

import threading
from typing import Generic, TypeVar

FrameItem = TypeVar("FrameItem")


class LatestFrameScheduler(Generic[FrameItem]):
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending: dict[int, FrameItem] = {}
        self._last_camera_id: int | None = None
        self._replaced: dict[int, int] = {}
        self._stopped = False

    def submit(self, camera_id: int, item: FrameItem) -> None:
        with self._condition:
            if self._stopped:
                return
            if camera_id in self._pending:
                self._replaced[camera_id] = self._replaced.get(camera_id, 0) + 1
            self._pending[camera_id] = item
            self._condition.notify()

    def take(self, timeout: float = 0.25) -> FrameItem | None:
        with self._condition:
            while not self._pending and not self._stopped:
                self._condition.wait(timeout=timeout)
            if self._stopped or not self._pending:
                return None
            ids = sorted(self._pending)
            camera_id = next(
                (
                    item
                    for item in ids
                    if self._last_camera_id is None or item > self._last_camera_id
                ),
                ids[0],
            )
            self._last_camera_id = camera_id
            return self._pending.pop(camera_id)

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._pending.clear()
            self._condition.notify_all()

    def metrics(self) -> dict[int, int]:
        with self._condition:
            return dict(self._replaced)
