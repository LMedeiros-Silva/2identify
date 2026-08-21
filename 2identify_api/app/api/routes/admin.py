"""Authenticated, read-only administrative endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_admin_dashboard_service, get_current_admin
from app.schemas import AdminDashboardSummary, AdministratorPayload
from app.services import AdminDashboardService, AdministratorPrincipal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["administration"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_PROTECTED_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Token administrativo inválido"},
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "description": "Serviço administrativo indisponível"
    },
}


@router.get(
    "/me",
    response_model=AdministratorPayload,
    responses=_PROTECTED_RESPONSES,
)
def get_admin_identity(
    response: Response,
    administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
) -> AdministratorPayload:
    """Return the database-revalidated administrator identity."""

    response.headers.update(_NO_STORE_HEADERS)
    return AdministratorPayload(
        id=administrator.account_id,
        name=administrator.name,
        username=administrator.username,
        profile="administrador",
    )


@router.get(
    "/dashboard/summary",
    response_model=AdminDashboardSummary,
    responses=_PROTECTED_RESPONSES,
)
def get_admin_dashboard_summary(
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[
        AdminDashboardService,
        Depends(get_admin_dashboard_service),
    ],
) -> AdminDashboardSummary:
    """Return read-only employee, PPE-delivery and alert counters."""

    try:
        summary = service.get_summary()
    except SQLAlchemyError as error:
        logger.error(
            "admin_dashboard_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço administrativo indisponível.",
            headers=_NO_STORE_HEADERS,
        ) from error

    response.headers.update(_NO_STORE_HEADERS)
    return AdminDashboardSummary(
        active_employees=summary.active_employees,
        ppe_assignments=summary.ppe_assignments,
        delivered_ppe=summary.delivered_ppe,
        ppe_delivery_percentage=summary.ppe_delivery_percentage,
        alerts=summary.alerts,
        critical_alerts=summary.critical_alerts,
        generated_at=summary.generated_at,
    )
