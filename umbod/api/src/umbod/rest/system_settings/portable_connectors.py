from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StrictBool

from umbod.core.system_settings import UpdatePortableConnectorSettings

from .dependencies import SystemSettingsAccess
from .route_policy import SystemSettingsRoute

router = APIRouter(prefix="/portable-connectors", route_class=SystemSettingsRoute)


class PortableConnectorsSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


class PortableConnectorsSettingsResponse(BaseModel):
    enabled: bool


@router.get("")
async def get_portable_connectors_settings(
    access: SystemSettingsAccess,
) -> PortableConnectorsSettingsResponse:
    await access.ensure_ready()
    enabled = await access.service.get_portable_connectors_enabled(access.actor)
    return PortableConnectorsSettingsResponse(enabled=enabled)


@router.patch("")
async def patch_portable_connectors_settings(
    body: PortableConnectorsSettingsPatch,
    access: SystemSettingsAccess,
) -> PortableConnectorsSettingsResponse:
    await access.ensure_ready()
    enabled = await access.service.set_portable_connectors_enabled(
        access.actor,
        UpdatePortableConnectorSettings(portable_connectors_enabled=body.enabled),
    )
    return PortableConnectorsSettingsResponse(enabled=enabled)
