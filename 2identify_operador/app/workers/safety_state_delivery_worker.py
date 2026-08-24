"""Bounded retry worker for Operator-to-API safety snapshots."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.services.safety_state_service import (
    SafetyStateDeliveryError,
    SafetyStateDeliveryRejectedError,
    SafetyStateDeliveryUnavailableError,
    SafetyStateSender,
    SafetyStateSnapshot,
)

logger = logging.getLogger(__name__)


class SafetyStateDeliveryWorker(QThread):
    delivered = Signal(object)
    delivery_failed = Signal(str)

    def __init__(
        self,
        sender: SafetyStateSender,
        snapshot: SafetyStateSnapshot,
        access_token: str,
        *,
        maximum_attempts: int,
        retry_delay_seconds: float,
    ) -> None:
        super().__init__()
        if maximum_attempts < 1 or retry_delay_seconds < 0:
            raise ValueError("política de repetição inválida")
        self.setObjectName(f"SafetyStateDeliveryWorker-{snapshot.work_session_id}")
        self._sender = sender
        self._snapshot = snapshot
        self._access_token = access_token
        self._maximum_attempts = maximum_attempts
        self._retry_delay_ms = round(retry_delay_seconds * 1_000)

    @property
    def snapshot(self) -> SafetyStateSnapshot:
        return self._snapshot

    def run(self) -> None:
        for attempt in range(1, self._maximum_attempts + 1):
            if self.isInterruptionRequested():
                return
            try:
                receipt = self._sender.send_safety_state(
                    self._snapshot,
                    self._access_token,
                )
            except SafetyStateDeliveryRejectedError as error:
                self.delivery_failed.emit(str(error))
                return
            except SafetyStateDeliveryUnavailableError as error:
                if attempt == self._maximum_attempts:
                    self.delivery_failed.emit(str(error))
                    return
                logger.warning(
                    "safety_state_delivery_retry_scheduled",
                    extra={
                        "work_session_id": str(self._snapshot.work_session_id),
                        "attempt": attempt,
                    },
                )
                if self._retry_delay_ms:
                    self.msleep(self._retry_delay_ms)
            except SafetyStateDeliveryError as error:
                self.delivery_failed.emit(str(error))
                return
            except Exception:
                logger.exception(
                    "safety_state_delivery_unexpected_failure",
                    extra={"work_session_id": str(self._snapshot.work_session_id)},
                )
                self.delivery_failed.emit(
                    "Falha inesperada ao atualizar o sinalizador."
                )
                return
            else:
                self.delivered.emit(receipt)
                return
