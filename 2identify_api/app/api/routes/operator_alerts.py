"""Authenticated alert-ingestion endpoint used by the Operator desktop app."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import (
    get_current_operator,
    get_operator_alert_service,
    get_realtime_event_broker,
)
from app.realtime import RealtimeEventBroker
from app.repositories import AlertEventConflictError
from app.schemas import OperatorAlertCreate, OperatorAlertReceipt
from app.services import OperatorAlertService, OperatorPrincipal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/operator", tags=["operator-alerts"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.post(
    "/alerts",
    response_model=OperatorAlertReceipt,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"description": "Evento idempotente já persistido"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Operador não autorizado"},
        status.HTTP_409_CONFLICT: {"description": "event_id reutilizado"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Persistência indisponível"},
    },
)
def ingest_operator_alert(
    payload: OperatorAlertCreate,
    response: Response,
    background_tasks: BackgroundTasks,
    principal: Annotated[OperatorPrincipal, Depends(get_current_operator)],
    service: Annotated[OperatorAlertService, Depends(get_operator_alert_service)],
    broker: Annotated[RealtimeEventBroker, Depends(get_realtime_event_broker)],
) -> OperatorAlertReceipt:
    try:
        result = service.ingest(payload, operator_id=principal.account_id)
    except AlertEventConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Identificador do evento já utilizado.",
            headers=_NO_STORE_HEADERS,
        ) from error
    except SQLAlchemyError as error:
        logger.error(
            "operator_alert_persistence_unavailable",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível registrar o alerta.",
            headers=_NO_STORE_HEADERS,
        ) from error
    response.headers.update(_NO_STORE_HEADERS)
    if result.stored.duplicate:
        response.status_code = status.HTTP_200_OK
    else:
        background_tasks.add_task(broker.publish, result.event)
    return OperatorAlertReceipt(
        event_id=result.stored.event_id,
        alert_id=result.stored.alert_id,
        occurrence_id=result.stored.occurrence_id,
        duplicate=result.stored.duplicate,
    )
