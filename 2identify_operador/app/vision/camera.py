"""OpenCV camera adapter with bounded open/read behavior when supported."""

from __future__ import annotations

from typing import Protocol

import cv2

from app.vision.types import Frame


class CameraSession(Protocol):
    def open(self) -> bool: ...

    def read(self) -> tuple[bool, Frame | None]: ...

    def close(self) -> None: ...


class OpenCVCameraSession:
    """Own a VideoCapture instance inside the worker that consumes it."""

    def __init__(
        self,
        source: int | str,
        width: int,
        height: int,
        open_timeout_ms: int,
        read_timeout_ms: int,
    ) -> None:
        self._source = source
        self._width = width
        self._height = height
        self._open_timeout_ms = open_timeout_ms
        self._read_timeout_ms = read_timeout_ms
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self.close()
        capture = cv2.VideoCapture()
        self._set_if_supported(capture, "CAP_PROP_OPEN_TIMEOUT_MSEC", self._open_timeout_ms)
        self._set_if_supported(capture, "CAP_PROP_READ_TIMEOUT_MSEC", self._read_timeout_ms)
        opened = bool(capture.open(self._source, cv2.CAP_ANY))
        if not opened:
            capture.release()
            return False

        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._set_if_supported(capture, "CAP_PROP_BUFFERSIZE", 1)
        self._capture = capture
        return True

    def read(self) -> tuple[bool, Frame | None]:
        capture = self._capture
        if capture is None or not capture.isOpened():
            return False, None
        success, frame = capture.read()
        return bool(success), frame if success else None

    def close(self) -> None:
        capture = self._capture
        self._capture = None
        if capture is not None:
            capture.release()

    @staticmethod
    def _set_if_supported(capture: cv2.VideoCapture, property_name: str, value: float) -> None:
        property_id = getattr(cv2, property_name, None)
        if property_id is not None:
            capture.set(property_id, value)

