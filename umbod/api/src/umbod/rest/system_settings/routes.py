from fastapi import APIRouter

from .filesystem import router as filesystem_router

router = APIRouter(prefix="/system-settings", tags=["system-settings"])
router.include_router(filesystem_router)
