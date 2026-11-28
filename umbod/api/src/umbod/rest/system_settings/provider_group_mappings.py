from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from umbod.core.system_settings.provider_group_mappings import (
    EffectiveProviderGroupMappings,
    ProviderGroupMappings,
    ProviderGroupMappingsService,
    UnregisteredMappingGroups,
)

from .dependencies import AuthorizedSettings, get_authorized_provider_group_mappings
from .route_policy import SystemSettingsRoute

router = APIRouter(prefix="/provider-group-mappings", route_class=SystemSettingsRoute)
MappingsAccess = Annotated[
    AuthorizedSettings[ProviderGroupMappingsService],
    Depends(get_authorized_provider_group_mappings),
]


class SetProviderGroupMappings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["set"]
    mappings: ProviderGroupMappings


class ResetProviderGroupMappings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["reset"]


@router.get("")
async def get_provider_group_mappings(
    access: MappingsAccess,
) -> EffectiveProviderGroupMappings:
    await access.ensure_ready()
    return await access.service.get(access.actor)


@router.patch("")
async def patch_provider_group_mappings(
    body: Annotated[
        SetProviderGroupMappings | ResetProviderGroupMappings,
        Body(discriminator="operation"),
    ],
    access: MappingsAccess,
) -> EffectiveProviderGroupMappings:
    await access.ensure_ready()
    if isinstance(body, ResetProviderGroupMappings):
        return await access.service.reset(access.actor)
    try:
        return await access.service.replace(access.actor, body.mappings)
    except UnregisteredMappingGroups as error:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "mappings", index, "group_id"],
                    "type": "unregistered_group",
                    "msg": "Mapping target group is not registered",
                }
                for index in error.indexes
            ],
        ) from None
