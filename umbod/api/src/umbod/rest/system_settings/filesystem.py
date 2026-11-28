from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import ConfigDict, Field, StrictBool

from umbod.proxies import Model
from umbod.core.system_settings import (
    EffectiveFilesystemSettings,
    SettingsSource,
    UpdateSystemSettings,
)

from .dependencies import SystemSettingsAccess
from .route_policy import SystemSettingsRoute

router = APIRouter(prefix="/filesystem", route_class=SystemSettingsRoute)


class SetDeletionApproval(Model):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["set"]
    value: StrictBool


class ResetDeletionApproval(Model):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["reset"]


class FilesystemSettingsPatch(Model):
    model_config = ConfigDict(extra="forbid")

    require_mcp_file_deletion_approval: Annotated[
        SetDeletionApproval | ResetDeletionApproval, Field(discriminator="operation")
    ]


class DeletionApprovalSetting(Model):
    value: bool
    source: SettingsSource


class FilesystemSettingsResponse(Model):
    require_mcp_file_deletion_approval: DeletionApprovalSetting


def _filesystem_response(
    effective: EffectiveFilesystemSettings,
) -> FilesystemSettingsResponse:
    return FilesystemSettingsResponse(
        require_mcp_file_deletion_approval=DeletionApprovalSetting(
            value=effective.settings.require_mcp_file_deletion_approval,
            source=effective.source,
        )
    )


@router.get("")
async def get_filesystem_settings(
    access: SystemSettingsAccess,
) -> FilesystemSettingsResponse:
    await access.ensure_ready()
    return _filesystem_response(
        await access.service.get_effective_settings(access.actor)
    )


@router.patch("")
async def patch_filesystem_settings(
    body: FilesystemSettingsPatch,
    access: SystemSettingsAccess,
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
