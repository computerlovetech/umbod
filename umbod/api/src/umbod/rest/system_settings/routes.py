from fastapi import APIRouter

from .filesystem import router as filesystem_router
from .provider_group_mappings import router as provider_group_mappings_router

router = APIRouter(prefix="/system-settings", tags=["system-settings"])
router.include_router(filesystem_router)
router.include_router(provider_group_mappings_router)
