"""Authenticated employee registration and biometric template endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_admin
from app.core.database import get_db
from app.repositories.admin_employee_repository import (
    AdminEmployeeRepository,
    EmployeeConflictError,
    EmployeeNotFoundError,
)
from app.schemas.admin_employees import (
    EmployeeDetail,
    EmployeeDraft,
    EmployeeList,
    FaceTemplateDraft,
    FaceTemplateStatus,
)
from app.services import AdministratorPrincipal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/employees", tags=["administrative-employees"])
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _repository(session: Annotated[Session, Depends(get_db)]) -> AdminEmployeeRepository:
    return AdminEmployeeRepository(session)


@router.get("", response_model=EmployeeList)
def list_employees(
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    repository: Annotated[AdminEmployeeRepository, Depends(_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EmployeeList:
    response.headers.update(_NO_STORE)
    try:
        items, total = repository.list(limit=limit, offset=offset)
        return EmployeeList(items=items, total=total, limit=limit, offset=offset)
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.get("/{employee_id}", response_model=EmployeeDetail)
def get_employee(
    employee_id: int,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    repository: Annotated[AdminEmployeeRepository, Depends(_repository)],
) -> EmployeeDetail:
    response.headers.update(_NO_STORE)
    try:
        return repository.get(employee_id)
    except EmployeeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error), headers=_NO_STORE) from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.post("", response_model=EmployeeDetail, status_code=status.HTTP_201_CREATED)
def create_employee(
    draft: EmployeeDraft,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    repository: Annotated[AdminEmployeeRepository, Depends(_repository)],
) -> EmployeeDetail:
    response.headers.update(_NO_STORE)
    try:
        return repository.create(draft)
    except EmployeeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error), headers=_NO_STORE) from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.put("/{employee_id}", response_model=EmployeeDetail)
def update_employee(
    employee_id: int,
    draft: EmployeeDraft,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    repository: Annotated[AdminEmployeeRepository, Depends(_repository)],
) -> EmployeeDetail:
    response.headers.update(_NO_STORE)
    try:
        return repository.update(employee_id, draft)
    except EmployeeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error), headers=_NO_STORE) from error
    except EmployeeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error), headers=_NO_STORE) from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.get("/{employee_id}/face-template", response_model=FaceTemplateStatus)
def get_face_status(
    employee_id: int,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    repository: Annotated[AdminEmployeeRepository, Depends(_repository)],
) -> FaceTemplateStatus:
    response.headers.update(_NO_STORE)
    try:
        return repository.face_status(employee_id)
    except EmployeeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error), headers=_NO_STORE) from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


@router.put("/{employee_id}/face-template", response_model=FaceTemplateStatus)
def put_face_template(
    employee_id: int,
    draft: FaceTemplateDraft,
    response: Response,
    _administrator: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    repository: Annotated[AdminEmployeeRepository, Depends(_repository)],
) -> FaceTemplateStatus:
    response.headers.update(_NO_STORE)
    try:
        return repository.save_face_template(employee_id, draft)
    except EmployeeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error), headers=_NO_STORE) from error
    except SQLAlchemyError as error:
        raise _unavailable(error) from error


def _unavailable(error: SQLAlchemyError) -> HTTPException:
    logger.error("admin_employee_database_unavailable", extra={"error_type": type(error).__name__})
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Cadastro de funcionários indisponível.",
        headers=_NO_STORE,
    )


__all__ = ["router"]
