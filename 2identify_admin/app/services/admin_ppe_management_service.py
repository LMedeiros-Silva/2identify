"""Read the authoritative snapshot through the authenticated API only."""

from typing import Protocol

from app.domain.ppe_management import ActiveOperationSnapshot


class AdminPpeManagementProvider(Protocol):
    def get_active_operations(self, access_token: str) -> tuple[ActiveOperationSnapshot, ...]: ...


class AdminPpeManagementService:
    def __init__(self, provider: AdminPpeManagementProvider) -> None:
        self._provider = provider

    def load(self, access_token: str) -> tuple[ActiveOperationSnapshot, ...]:
        return self._provider.get_active_operations(access_token)
