from typing import Annotated

from fastapi import APIRouter, Depends, Response

from umbod.core.admin_overview.models import AdminOverview
from umbod.core.admin_overview.service import AdminOverviewService

from .dependencies import get_admin_overview_service

router = APIRouter(prefix="/overview", tags=["admin-overview"])


@router.get("", response_model=AdminOverview)
async def read_overview(
    response: Response,
    service: Annotated[AdminOverviewService, Depends(get_admin_overview_service)],
) -> AdminOverview:
    response.headers["Cache-Control"] = "no-store"
    return await service.read()
