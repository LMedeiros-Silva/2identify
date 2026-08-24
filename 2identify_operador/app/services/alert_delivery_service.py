"""Contracts for authenticated delivery of locally raised safety alerts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain import SafetyAlert


class AlertDeliveryError(RuntimeError):
    """Base delivery failure safe to surface without transport internals."""


class AlertDeliveryUnavailableError(AlertDeliveryError):
    """Transient failure which can be retried with the same event UUID."""


class AlertDeliveryRejectedError(AlertDeliveryError):
    """Permanent authentication, validation or idempotency rejection."""


@dataclass(frozen=True, slots=True)
class AlertDeliveryReceipt:
    event_id: UUID
    alert_id: int
    occurrence_id: int
    duplicate: bool


class AlertSender(Protocol):
    def send_alert(
        self,
        alert: SafetyAlert,
        access_token: str,
    ) -> AlertDeliveryReceipt: ...
