from fastapi import APIRouter

from .oauth_routes import router as oauth_router
from .routes import router as connections_router

router = APIRouter()
router.include_router(connections_router)
router.include_router(oauth_router)

__all__ = ["router"]
