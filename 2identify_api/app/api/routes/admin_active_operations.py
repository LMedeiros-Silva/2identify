"""Administrative initial snapshot for realtime PPE management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_active_operation_registry, get_current_admin
from app.schemas import ActiveOperationSnapshot
from app.services import ActiveOperationRegistry, AdministratorPrincipal

router = APIRouter(prefix="/admin", tags=["administration-ppe"])
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get(
    "/active-operations",
    response_model=tuple[ActiveOperationSnapshot, ...],
)
async def list_active_operations(
    response: Response,
    _admin: Annotated[AdministratorPrincipal, Depends(get_current_admin)],
    registry: Annotated[
        ActiveOperationRegistry,
        Depends(get_active_operation_registry),
    ],
) -> tuple[ActiveOperationSnapshot, ...]:
    response.headers.update(_NO_STORE_HEADERS)
    return await registry.list_active()


__all__ = ["router"]
