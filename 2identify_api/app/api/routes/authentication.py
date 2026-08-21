"""Operator credential authentication endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_authentication_service
from app.schemas import (
    CredentialLoginRequest,
    CredentialLoginResponse,
    OperatorPayload,
)
from app.services import AuthenticationRejectedError, AuthenticationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.post(
    "/login",
    response_model=CredentialLoginResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Credenciais rejeitadas"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Autoridade de autenticação indisponível"
        },
    },
)
def login_with_credentials(
    payload: CredentialLoginRequest,
    response: Response,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> CredentialLoginResponse:
    """Authenticate an existing active account and return a signed bearer token."""

    try:
        account = service.authenticate(payload.username, payload.password)
    except AuthenticationRejectedError as error:
        logger.warning("credential_authentication_rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer", **_NO_STORE_HEADERS},
        ) from error
    except SQLAlchemyError as error:
        logger.error(
            "credential_authentication_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de autenticação indisponível.",
            headers=_NO_STORE_HEADERS,
        ) from error

    response.headers.update(_NO_STORE_HEADERS)
    logger.info(
        "credential_authentication_succeeded",
        extra={"account_id": account.account_id, "profile": account.profile},
    )
    return CredentialLoginResponse(
        access_token=account.access_token,
        expires_in=account.expires_in_seconds,
        operator=OperatorPayload(
            id=account.account_id,
            name=account.name,
            profile=account.profile,
            profile_photo_reference=None,
        ),
    )
