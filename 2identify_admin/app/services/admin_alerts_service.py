"""Desktop-facing administrative alert use cases."""

from __future__ import annotations

from typing import Protocol

from app.domain import AdminAlert, AdminAlertPage


class AdminAlertsProvider(Protocol):
    def get_alerts(self, access_token: str) -> AdminAlertPage: ...

    def confirm_alert(self, access_token: str, alert_id: int) -> AdminAlert: ...

    def close_alert(self, access_token: str, alert_id: int) -> AdminAlert: ...


class AdminAlertsService:
    def __init__(self, provider: AdminAlertsProvider) -> None:
        self._provider = provider

    def list_alerts(self, access_token: str) -> AdminAlertPage:
        return self._provider.get_alerts(access_token)

    def confirm_alert(self, access_token: str, alert_id: int) -> AdminAlert:
        return self._provider.confirm_alert(access_token, alert_id)

    def close_alert(self, access_token: str, alert_id: int) -> AdminAlert:
        return self._provider.close_alert(access_token, alert_id)


__all__ = ["AdminAlertsProvider", "AdminAlertsService"]
