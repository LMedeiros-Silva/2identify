"""Read-only operation configuration consumed by authenticated operators."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_current_operator, get_operations_service
from app.schemas import OperationDetail
from app.services import OperationsService, OperatorPrincipal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/operator/operations", tags=["operator-operations"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("", response_model=tuple[OperationDetail, ...])
def list_operator_operations(
    response: Response,
    _operator: Annotated[OperatorPrincipal, Depends(get_current_operator)],
    service: Annotated[OperationsService, Depends(get_operations_service)],
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
