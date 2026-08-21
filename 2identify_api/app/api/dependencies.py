"""FastAPI dependency composition for application services."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from app.core.config import Settings
from app.core.database import get_db
from app.core.security import AccessTokenService
from app.realtime import AdminRealtimeAuthorizer, RealtimeEventBroker
from app.repositories import DashboardRepository, UserRepository
from app.services import (
    AdminAuthorizationRejectedError,
    AdminAuthorizationService,
    AdminDashboardService,
    AdministratorPrincipal,
    AuthenticationService,
)

logger = logging.getLogger(__name__)
_ADMIN_PROFILE = frozenset({"administrador"})
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_ADMIN_BEARER = HTTPBearer(auto_error=False, scheme_name="AdminBearer")


def get_runtime_settings(connection: HTTPConnection) -> Settings:
    settings = getattr(connection.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("configuração da aplicação não disponível")
    return settings


def get_realtime_event_broker(connection: HTTPConnection) -> RealtimeEventBroker:
    broker = getattr(connection.app.state, "realtime_event_broker", None)
    if not isinstance(broker, RealtimeEventBroker):
        raise RuntimeError("broker de eventos em tempo real não disponível")
    return broker


def get_admin_realtime_authorizer(
    connection: HTTPConnection,
) -> AdminRealtimeAuthorizer:
    authorizer = getattr(connection.app.state, "admin_realtime_authorizer", None)
    if not isinstance(authorizer, AdminRealtimeAuthorizer):
        raise RuntimeError("autorização administrativa em tempo real não disponível")
    return authorizer


def get_authentication_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> AuthenticationService:
    return AuthenticationService(
        repository=UserRepository(session),
        tokens=AccessTokenService(settings),
        allowed_profiles=settings.auth_allowed_profiles,
    )


def get_admin_authentication_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> AuthenticationService:
    return AuthenticationService(
        repository=UserRepository(session),
        tokens=AccessTokenService(
            settings,
            audience=settings.auth_admin_token_audience,
        ),
        allowed_profiles=_ADMIN_PROFILE,
    )


def get_admin_authorization_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> AdminAuthorizationService:
    return AdminAuthorizationService(
        repository=UserRepository(session),
        tokens=AccessTokenService(
            settings,
            audience=settings.auth_admin_token_audience,
        ),
    )


def get_current_admin(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_ADMIN_BEARER),
    ],
    service: Annotated[
        AdminAuthorizationService,
        Depends(get_admin_authorization_service),
    ],
) -> AdministratorPrincipal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação administrativa necessária.",
            headers={"WWW-Authenticate": "Bearer", **_NO_STORE_HEADERS},
        )

    try:
        return service.authorize(credentials.credentials)
    except AdminAuthorizationRejectedError as error:
        logger.warning("admin_bearer_authorization_rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso inválido.",
            headers={"WWW-Authenticate": "Bearer", **_NO_STORE_HEADERS},
        ) from error
    except SQLAlchemyError as error:
        logger.error(
            "admin_bearer_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço administrativo indisponível.",
            headers=_NO_STORE_HEADERS,
        ) from error


def get_admin_dashboard_service(
    session: Annotated[Session, Depends(get_db)],
) -> AdminDashboardService:
    return AdminDashboardService(DashboardRepository(session))
