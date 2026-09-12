"""Application route modules."""

from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.admin_active_operations import router as admin_active_operations_router
from app.api.routes.admin_alerts import router as admin_alerts_router
from app.api.routes.admin_authentication import router as admin_authentication_router
from app.api.routes.admin_operations import router as admin_operations_router
from app.api.routes.admin_realtime import router as admin_realtime_router
from app.api.routes.authentication import router as authentication_router
from app.api.routes.device_safety import router as device_safety_router
from app.api.routes.foundation import router as foundation_router
from app.api.routes.operator_alerts import router as operator_alerts_router
from app.api.routes.operator_operations import router as operator_operations_router
from app.api.routes.operator_safety_state import router as operator_safety_state_router

router = APIRouter()
router.include_router(foundation_router)
router.include_router(authentication_router)
router.include_router(admin_authentication_router)
router.include_router(admin_router)
router.include_router(admin_active_operations_router)
router.include_router(admin_alerts_router)
router.include_router(admin_operations_router)
router.include_router(admin_realtime_router)
router.include_router(device_safety_router)
router.include_router(operator_alerts_router)
router.include_router(operator_operations_router)
router.include_router(operator_safety_state_router)

__all__ = ["router"]
