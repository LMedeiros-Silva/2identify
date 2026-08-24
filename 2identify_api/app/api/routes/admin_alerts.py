"""Authenticated administrative alert workflow."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_admin_alerts_service, get_current_admin
from app.repositories import AdminAlertNotFoundError, AdminAlertStateConflictError
from app.schemas import AdminAlertActionRequest, AdminAlertDetail, AdminAlertList
from app.services import AdminAlertsService, AdministratorPrincipal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/alerts", tags=["administrative-alerts"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("", response_model=AdminAlertList)
def list_admin_alerts(
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[AdminAlertsService, Depends(get_admin_alerts_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    alert_status: Annotated[
        Literal["nao_lido", "lido", "encerrado"] | None,
        Query(alias="status"),
    ] = None,
) -> AdminAlertList:
    response.headers.update(_NO_STORE_HEADERS)
    try:
        return service.list_alerts(
            limit=limit,
            offset=offset,
            status_filter=alert_status,
        )
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.get("/{alert_id}", response_model=AdminAlertDetail)
def get_admin_alert(
    alert_id: int,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[AdminAlertsService, Depends(get_admin_alerts_service)],
) -> AdminAlertDetail:
    response.headers.update(_NO_STORE_HEADERS)
    try:
        return service.get_alert(alert_id)
    except AdminAlertNotFoundError as error:
        raise _not_found() from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.patch("/{alert_id}/confirm", response_model=AdminAlertDetail)
def confirm_admin_alert(
    alert_id: int,
    payload: AdminAlertActionRequest,
    response: Response,
    administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[AdminAlertsService, Depends(get_admin_alerts_service)],
) -> AdminAlertDetail:
    response.headers.update(_NO_STORE_HEADERS)
    try:
        return service.confirm_alert(
            alert_id,
            administrator_id=administrator.account_id,
            observation=payload.observation,
        )
    except AdminAlertNotFoundError as error:
        raise _not_found() from error
    except AdminAlertStateConflictError as error:
        raise _conflict(str(error)) from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.patch("/{alert_id}/close", response_model=AdminAlertDetail)
def close_admin_alert(
    alert_id: int,
    payload: AdminAlertActionRequest,
    response: Response,
    administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[AdminAlertsService, Depends(get_admin_alerts_service)],
) -> AdminAlertDetail:
    response.headers.update(_NO_STORE_HEADERS)
    try:
        return service.close_alert(
            alert_id,
            administrator_id=administrator.account_id,
            observation=payload.observation,
        )
    except AdminAlertNotFoundError as error:
        raise _not_found() from error
    except AdminAlertStateConflictError as error:
        raise _conflict(str(error)) from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Alerta não encontrado.",
        headers=_NO_STORE_HEADERS,
    )


def _conflict(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=message,
        headers=_NO_STORE_HEADERS,
    )


def _unavailable(error: SQLAlchemyError) -> HTTPException:
    logger.error(
        "admin_alert_database_unavailable",
        extra={"error_type": type(error).__name__},
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Serviço de alertas indisponível.",
        headers=_NO_STORE_HEADERS,
    )


__all__ = ["router"]
