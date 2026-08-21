"""Objetos de domínio independentes de UI, transporte e banco de dados."""

from app.domain.admin import (
    AdminAuthentication,
    AdminCredentials,
    Administrator,
    DashboardSummary,
)
from app.domain.realtime import (
    ConnectionReadyEvent,
    HeartbeatEvent,
    RealtimeAlert,
    RealtimeEvent,
)

__all__ = [
    "AdminAuthentication",
    "AdminCredentials",
    "Administrator",
    "DashboardSummary",
    "ConnectionReadyEvent",
    "HeartbeatEvent",
    "RealtimeAlert",
    "RealtimeEvent",
]
