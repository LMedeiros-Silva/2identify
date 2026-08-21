"""Short-lived database authorization checks for administrative streams."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import AccessTokenService
from app.repositories import UserRepository
from app.services import AdminAuthorizationService, AdministratorPrincipal

SessionFactory = Callable[[], Session]


@runtime_checkable
class AdminRealtimeAuthorizer(Protocol):
    """Revalidate one admin token without retaining a database session."""

    def authorize(self, token: str) -> AdministratorPrincipal: ...


class DatabaseAdminRealtimeAuthorizer:
    """Open and close a fresh SQLAlchemy session for every authorization check."""

    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._tokens = AccessTokenService(
            settings,
            audience=settings.auth_admin_token_audience,
        )

    def authorize(self, token: str) -> AdministratorPrincipal:
        with self._session_factory() as session:
            service = AdminAuthorizationService(
                repository=UserRepository(session),
                tokens=self._tokens,
            )
            return service.authorize(token)


class UnavailableAdminRealtimeAuthorizer:
    """Fail closed when an application fixture has no session factory."""

    def authorize(self, _token: str) -> AdministratorPrincipal:
        raise RuntimeError("autorização em tempo real indisponível")


__all__ = [
    "AdminRealtimeAuthorizer",
    "DatabaseAdminRealtimeAuthorizer",
    "SessionFactory",
    "UnavailableAdminRealtimeAuthorizer",
]
