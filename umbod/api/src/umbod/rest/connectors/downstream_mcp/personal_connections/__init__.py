from fastapi import APIRouter

from .authorization import router as authorization_router
from .refresh_routes import router as refresh_router
from .oauth_routes import router as oauth_router
from .routes import router as connections_router
from .tools import router as tools_router

router = APIRouter()
router.include_router(connections_router)
router.include_router(authorization_router)
router.include_router(refresh_router)
router.include_router(oauth_router)
router.include_router(tools_router)

__all__ = ["router"]
