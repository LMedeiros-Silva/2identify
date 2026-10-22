"""Operator credential authentication endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import (
    get_authentication_service,
    get_face_authentication_service,
    require_operator_station,
)
from app.schemas import (
    CredentialLoginRequest,
    CredentialLoginResponse,
    FaceLoginRequest,
    OperatorPayload,
)
from app.services import AuthenticationRejectedError, AuthenticationService
from app.services.face_authentication import (
    EMPLOYEE_PROFILE,
    FaceAuthenticationRejectedError,
    FaceAuthenticationService,
)

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


@router.post(
    "/face",
    response_model=CredentialLoginResponse,
    dependencies=[Depends(require_operator_station)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Rosto ou funcionário não autorizado"},
        status.HTTP_403_FORBIDDEN: {"description": "Estação não autorizada"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Face ID indisponível"},
    },
)
def login_with_face(
    payload: FaceLoginRequest,
    response: Response,
    service: Annotated[FaceAuthenticationService, Depends(get_face_authentication_service)],
) -> CredentialLoginResponse:
    """Identify the employee from live-frame embeddings and return their session token."""

    try:
        employee = service.authenticate(payload.model_id, payload.probes)
    except FaceAuthenticationRejectedError as error:
        # Never log the embeddings; the reason alone tells unknown face from replay.
        logger.warning("face_authentication_rejected", extra={"reason": str(error)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Rosto não reconhecido ou funcionário não autorizado.",
            headers={"WWW-Authenticate": "Bearer", **_NO_STORE_HEADERS},
        ) from error
    except SQLAlchemyError as error:
        logger.error(
            "face_authentication_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de autenticação indisponível.",
            headers=_NO_STORE_HEADERS,
        ) from error

    response.headers.update(_NO_STORE_HEADERS)
    logger.info("face_authentication_succeeded", extra={"employee_id": employee.employee_id})
    return CredentialLoginResponse(
        access_token=employee.access_token,
        expires_in=employee.expires_in_seconds,
        operator=OperatorPayload(
            id=employee.employee_id,
            name=employee.name,
            profile=EMPLOYEE_PROFILE,
            profile_photo_reference=None,
        ),
    )
