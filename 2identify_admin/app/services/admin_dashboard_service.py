from __future__ import annotations

from typing import Protocol

from app.domain import DashboardSummary


class AdminDashboardProvider(Protocol):
    def get_dashboard_summary(self, access_token: str) -> DashboardSummary: ...


class AdminDashboardService:
    """Expõe ao controller o resumo remoto do dashboard."""

    def __init__(self, provider: AdminDashboardProvider) -> None:
        self._provider = provider

    def get_summary(self, access_token: str) -> DashboardSummary:
        return self._provider.get_dashboard_summary(access_token)
