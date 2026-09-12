"""Authenticated safety snapshots produced by the Operator desktop app."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_active_operation_registry,
    get_current_operator,
    get_operations_service,
    get_operator_alert_service,
    get_safety_state_aggregator,
)
from app.repositories.operation_repository import OperationConfigurationNotFoundError
from app.schemas import OperatorSafetyStateSnapshot, SafetyStateMessage
from app.services import (
    ActiveOperationRegistry,
    ActiveOperationSnapshotConflictError,
    OperationsService,
    OperatorAlertService,
    OperatorPrincipal,
    SafetyStateAggregator,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/operator", tags=["operator-safety-state"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.put(
    "/safety-state",
    response_model=SafetyStateMessage,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Operador não autorizado"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Canal de hardware indisponível"},
    },
)
async def update_operator_safety_state(
    payload: OperatorSafetyStateSnapshot,
    principal: Annotated[OperatorPrincipal, Depends(get_current_operator)],
    aggregator: Annotated[SafetyStateAggregator, Depends(get_safety_state_aggregator)],
    registry: Annotated[
        ActiveOperationRegistry,
        Depends(get_active_operation_registry),
    ],
    operations: Annotated[OperationsService, Depends(get_operations_service)],
    safety_alerts: Annotated[OperatorAlertService, Depends(get_operator_alert_service)],
) -> SafetyStateMessage:
    """Replace one WorkSession snapshot and return the effective global state."""

    try:
        if payload.started_at is not None:
            operation = await run_in_threadpool(
                operations.get_operation,
                payload.operation_id,
            )
            await registry.update(
                operator_id=principal.account_id,
                operator_name=principal.name,
                operation=operation,
                snapshot=payload,
            )
        current = await aggregator.current()
        if current is None:
            current = (await aggregator.refresh(safety_alerts.active_conditions)).message
    except OperationConfigurationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A operação monitorada não existe.",
            headers=_NO_STORE_HEADERS,
        ) from error
    except ActiveOperationSnapshotConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
            headers=_NO_STORE_HEADERS,
        ) from error
    except SQLAlchemyError as error:
        logger.error(
            "operator_active_operation_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível validar a operação monitorada.",
            headers=_NO_STORE_HEADERS,
        ) from error
    except RuntimeError as error:
        logger.error(
            "operator_safety_state_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível atualizar o sinalizador de segurança.",
            headers=_NO_STORE_HEADERS,
        ) from error
    return current
