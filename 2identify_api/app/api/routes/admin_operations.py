"""Administrator-only operation and risk-area configuration endpoints."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.dependencies import get_current_admin, get_operations_service
from app.repositories import (
    OperationConfigurationConflictError,
    OperationConfigurationNotFoundError,
)
from app.schemas import (
    AdminCameraItem,
    CameraCatalogItem,
    CameraWrite,
    OperationCatalog,
    OperationDetail,
    OperationWrite,
    RiskAreaDetail,
    RiskAreaWrite,
)
from app.services import AdministratorPrincipal, OperationsService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["administrative-operations"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("/admin/operations/catalog", response_model=OperationCatalog)
def get_operation_catalog(
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> OperationCatalog:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(service.get_catalog)


@router.post(
    "/admin/cameras",
    response_model=CameraCatalogItem,
    status_code=status.HTTP_201_CREATED,
)
def create_camera(
    payload: CameraWrite,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> CameraCatalogItem:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.create_camera(payload))


@router.get("/admin/cameras", response_model=tuple[AdminCameraItem, ...])
def list_cameras(
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
    sector_id: Annotated[int | None, Query(gt=0)] = None,
) -> tuple[AdminCameraItem, ...]:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.list_cameras(sector_id))


@router.put("/admin/cameras/{camera_id}", response_model=AdminCameraItem)
def update_camera(
    camera_id: int,
    payload: CameraWrite,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> AdminCameraItem:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.update_camera(camera_id, payload))


@router.get("/admin/risk-areas", response_model=tuple[RiskAreaDetail, ...])
def list_risk_areas(
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
    camera_id: Annotated[int | None, Query(gt=0)] = None,
) -> tuple[RiskAreaDetail, ...]:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.list_risk_areas(camera_id))


@router.post(
    "/admin/risk-areas",
    response_model=RiskAreaDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_risk_area(
    payload: RiskAreaWrite,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> RiskAreaDetail:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.create_risk_area(payload))


@router.put("/admin/risk-areas/{risk_area_id}", response_model=RiskAreaDetail)
def update_risk_area(
    risk_area_id: int,
    payload: RiskAreaWrite,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> RiskAreaDetail:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.update_risk_area(risk_area_id, payload))


@router.get("/admin/operations", response_model=tuple[OperationDetail, ...])
def list_operations(
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> tuple[OperationDetail, ...]:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(service.list_operations)


@router.post(
    "/admin/operations",
    response_model=OperationDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_operation(
    payload: OperationWrite,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> OperationDetail:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.create_operation(payload))


@router.put("/admin/operations/{operation_id}", response_model=OperationDetail)
def update_operation(
    operation_id: int,
    payload: OperationWrite,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
) -> OperationDetail:
    response.headers.update(_NO_STORE_HEADERS)
    return _execute(lambda: service.update_operation(operation_id, payload))


def _execute[T](action: Callable[[], T]) -> T:
    try:
        return action()
    except OperationConfigurationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
            headers=_NO_STORE_HEADERS,
        ) from error
    except (OperationConfigurationConflictError, IntegrityError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                str(error)
                if isinstance(error, OperationConfigurationConflictError)
                else "configuração duplicada ou em uso"
            ),
            headers=_NO_STORE_HEADERS,
        ) from error
    except SQLAlchemyError as error:
        logger.error(
            "operation_configuration_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de configuração de operações indisponível.",
            headers=_NO_STORE_HEADERS,
        ) from error


__all__ = ["router"]
