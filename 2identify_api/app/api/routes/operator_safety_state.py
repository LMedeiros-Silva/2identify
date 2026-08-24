"""Authenticated safety snapshots produced by the Operator desktop app."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_operator, get_safety_state_aggregator
from app.schemas import OperatorSafetyStateSnapshot, SafetyStateMessage
from app.services import OperatorPrincipal, SafetyStateAggregator

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
) -> SafetyStateMessage:
    """Replace one WorkSession snapshot and return the effective global state."""

    try:
        result = await aggregator.update(
            operator_id=principal.account_id,
            snapshot=payload,
        )
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
    return result.message
