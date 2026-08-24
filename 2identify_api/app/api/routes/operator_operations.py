"""Read-only operation configuration consumed by authenticated operators."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import (
    get_current_operator,
    get_operations_service,
    get_runtime_settings,
)
from app.core.config import Settings
from app.schemas import OperationDetail
from app.services import OperationsService, OperatorPrincipal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/operator/operations", tags=["operator-operations"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_CATALOG_BEARER = HTTPBearer(auto_error=False, scheme_name="OperatorCatalogBearer")


@router.get("", response_model=tuple[OperationDetail, ...])
def list_operator_operations(
    response: Response,
    _operator: Annotated[OperatorPrincipal, Depends(get_current_operator)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> tuple[OperationDetail, ...]:
    return _list_active_operations(response, service)


@router.get(
    "/catalog",
    response_model=tuple[OperationDetail, ...],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Token do catálogo inválido"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Catálogo ou autenticação indisponível"
        },
    },
)
def list_operator_operations_for_trusted_workstation(
    response: Response,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_CATALOG_BEARER),
    ],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> tuple[OperationDetail, ...]:
    """Read the catalog without minting or impersonating an operator identity."""

    configured_token = settings.operator_catalog_token
    submitted_token = credentials.credentials if credentials is not None else None
    if configured_token is None:
        logger.error("operator_catalog_authentication_not_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação do catálogo de operações não configurada.",
            headers=_NO_STORE_HEADERS,
        )
    if submitted_token is None or not secrets.compare_digest(
        submitted_token,
        configured_token.get_secret_value(),
    ):
        logger.warning("operator_catalog_authorization_rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token do catálogo de operações inválido.",
            headers={"WWW-Authenticate": "Bearer", **_NO_STORE_HEADERS},
        )

    return _list_active_operations(response, service)


def _list_active_operations(
    response: Response,
    service: OperationsService,
) -> tuple[OperationDetail, ...]:
    response.headers.update(_NO_STORE_HEADERS)
    try:
        return service.list_operations(active_only=True)
    except SQLAlchemyError as error:
        logger.error(
            "operator_operations_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operações indisponíveis.",
            headers=_NO_STORE_HEADERS,
        ) from error


__all__ = ["router"]
