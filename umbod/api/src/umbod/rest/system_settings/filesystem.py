from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from umbod.core.system_settings import (
    EffectiveSystemSettings,
    SettingsSource,
    SystemSettingsService,
    UpdateSystemSettings,
)

from .dependencies import AuthorizedSettings, get_authorized_system_settings
from .route_policy import SystemSettingsRoute

router = APIRouter(prefix="/filesystem", route_class=SystemSettingsRoute)
SettingsAccess = Annotated[
    AuthorizedSettings[SystemSettingsService], Depends(get_authorized_system_settings)
]


class SetDeletionApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["set"]
    value: StrictBool


class ResetDeletionApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["reset"]


class FilesystemSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_mcp_file_deletion_approval: Annotated[
        SetDeletionApproval | ResetDeletionApproval, Field(discriminator="operation")
    ]


class DeletionApprovalSetting(BaseModel):
    value: bool
    source: SettingsSource


class FilesystemSettingsResponse(BaseModel):
    require_mcp_file_deletion_approval: DeletionApprovalSetting


def _filesystem_response(
    effective: EffectiveSystemSettings,
) -> FilesystemSettingsResponse:
    return FilesystemSettingsResponse(
        require_mcp_file_deletion_approval=DeletionApprovalSetting(
            value=effective.settings.require_mcp_file_deletion_approval,
            source=effective.source,
        )
    )


@router.get("")
async def get_filesystem_settings(access: SettingsAccess) -> FilesystemSettingsResponse:
    await access.ensure_ready()
    return _filesystem_response(
        await access.service.get_effective_settings(access.actor)
    )


@router.patch("")
async def patch_filesystem_settings(
    body: FilesystemSettingsPatch,
    access: SettingsAccess,
) -> FilesystemSettingsResponse:
    await access.ensure_ready()
    operation = body.require_mcp_file_deletion_approval
    if isinstance(operation, SetDeletionApproval):
        effective = await access.service.set_settings(
            access.actor,
            UpdateSystemSettings(require_mcp_file_deletion_approval=operation.value),
        )
    else:
        effective = await access.service.reset_mcp_file_deletion_approval(access.actor)
    return _filesystem_response(effective)
