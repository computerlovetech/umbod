from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, StrictBool

DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL: Final[bool] = True


class SystemSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    require_mcp_file_deletion_approval: StrictBool = (
        DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL
    )


class SettingsSource(StrEnum):
    ADMIN_OVERRIDE = "admin_override"
    DEPLOYMENT_DEFAULT = "deployment_default"
    BUILT_IN_DEFAULT = "built_in_default"


class EffectiveSystemSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    settings: SystemSettings
    source: SettingsSource


class UpdateSystemSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    require_mcp_file_deletion_approval: StrictBool
