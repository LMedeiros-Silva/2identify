"""Application route modules."""

from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.admin_authentication import router as admin_authentication_router
from app.api.routes.admin_realtime import router as admin_realtime_router
from app.api.routes.authentication import router as authentication_router
from app.api.routes.foundation import router as foundation_router

router = APIRouter()
router.include_router(foundation_router)
router.include_router(authentication_router)
router.include_router(admin_authentication_router)
router.include_router(admin_router)
router.include_router(admin_realtime_router)

__all__ = ["router"]
