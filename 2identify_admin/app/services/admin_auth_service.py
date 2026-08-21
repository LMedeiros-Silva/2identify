from __future__ import annotations

from typing import Protocol

from app.core.session import AdminSession
from app.domain import AdminAuthentication, AdminCredentials, Administrator
from app.services.errors import InvalidApiResponseError


class AdminAuthenticationProvider(Protocol):
    def login(self, credentials: AdminCredentials) -> AdminAuthentication: ...

    def get_current_administrator(self, access_token: str) -> Administrator: ...


class AdminAuthService:
    """Orquestra login e validação do token de administrador na API."""

    def __init__(self, provider: AdminAuthenticationProvider) -> None:
        self._provider = provider

    def authenticate(self, credentials: AdminCredentials) -> AdminAuthentication:
        authentication = self._provider.login(credentials)
        current = self._provider.get_current_administrator(
            authentication.access_token
        )

        if current.id != authentication.administrator.id:
            raise InvalidApiResponseError(
                "A identidade retornada pela API é inconsistente."
            )

        return AdminAuthentication(
            administrator=current,
            access_token=authentication.access_token,
            token_type=authentication.token_type,
            expires_in=authentication.expires_in,
        )

    def revalidate(self, session: AdminSession) -> Administrator:
        """Revalida um bearer rejeitado pelo WebSocket no endpoint `/admin/me`."""

        current = self._provider.get_current_administrator(session.access_token)
        if (
            current.id != session.administrator.id
            or current.profile != session.administrator.profile
        ):
            raise InvalidApiResponseError(
                "A identidade administrativa revalidada é inconsistente."
            )
        return current
