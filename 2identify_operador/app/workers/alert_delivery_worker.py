"""Bounded retry worker for authenticated safety-alert delivery."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.domain import SafetyAlert
from app.services.alert_delivery_service import (
    AlertDeliveryError,
    AlertDeliveryRejectedError,
    AlertDeliveryUnavailableError,
    AlertSender,
)

logger = logging.getLogger(__name__)


class AlertDeliveryWorker(QThread):
    delivered = Signal(object)
    delivery_failed = Signal(str, str)

    def __init__(
        self,
        sender: AlertSender,
        alert: SafetyAlert,
        access_token: str,
        *,
        maximum_attempts: int,
        retry_delay_seconds: float,
    ) -> None:
        super().__init__()
        if maximum_attempts < 1 or retry_delay_seconds < 0:
            raise ValueError("política de repetição inválida")
        self.setObjectName(f"AlertDeliveryWorker-{alert.alert_id}")
        self._sender = sender
        self._alert = alert
        self._access_token = access_token
        self._maximum_attempts = maximum_attempts
        self._retry_delay_ms = round(retry_delay_seconds * 1_000)

    @property
    def alert(self) -> SafetyAlert:
        return self._alert

    @property
    def event_id(self) -> str:
        return str(self._alert.alert_id)

    def run(self) -> None:
        for attempt in range(1, self._maximum_attempts + 1):
            if self.isInterruptionRequested():
                return
            try:
                receipt = self._sender.send_alert(self._alert, self._access_token)
            except AlertDeliveryRejectedError as error:
                self.delivery_failed.emit(self.event_id, str(error))
                return
            except AlertDeliveryUnavailableError as error:
                if attempt == self._maximum_attempts:
                    self.delivery_failed.emit(self.event_id, str(error))
                    return
                logger.warning(
                    "alert_delivery_retry_scheduled",
                    extra={"event_id": self.event_id, "attempt": attempt},
                )
                if self._retry_delay_ms:
                    self.msleep(self._retry_delay_ms)
            except AlertDeliveryError as error:
                self.delivery_failed.emit(self.event_id, str(error))
                return
            except Exception:
                logger.exception(
                    "alert_delivery_unexpected_failure",
                    extra={"event_id": self.event_id},
                )
                self.delivery_failed.emit(
                    self.event_id,
                    "Falha inesperada ao enviar o alerta.",
                )
                return
            else:
                self.delivered.emit(receipt)
                return
