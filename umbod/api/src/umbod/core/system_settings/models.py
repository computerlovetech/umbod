from enum import StrEnum
from typing import Final

from pydantic import ConfigDict, StrictBool

from umbod.proxies import Model

DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL: Final[bool] = True


class FilesystemSettings(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    require_mcp_file_deletion_approval: StrictBool = (
        DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL
    )


class SystemSettings(FilesystemSettings):
    portable_connectors_enabled: StrictBool = False


class SettingsSource(StrEnum):
    ADMIN_OVERRIDE = "admin_override"
    DEPLOYMENT_DEFAULT = "deployment_default"
    BUILT_IN_DEFAULT = "built_in_default"


class EffectiveFilesystemSettings(Model):
    model_config = ConfigDict(frozen=True)

    settings: FilesystemSettings
    source: SettingsSource


class UpdateSystemSettings(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    require_mcp_file_deletion_approval: StrictBool


class UpdatePortableConnectorSettings(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    portable_connectors_enabled: StrictBool
