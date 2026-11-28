from .errors import SettingsPermissionDenied, SettingsStorageUnavailable
from .models import (
    DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL,
    EffectiveFilesystemSettings,
    FilesystemSettings,
    SettingsSource,
    UpdatePortableConnectorSettings,
    UpdateSystemSettings,
)
from .ports import SettingsNotConfigured, SystemSettingsReader, SystemSettingsWriter


def require_administrator(actor_role: str) -> None:
    if actor_role != "administrator":
        raise SettingsPermissionDenied()


def _filesystem_result(
    settings: FilesystemSettings, source: SettingsSource
) -> EffectiveFilesystemSettings:
    return EffectiveFilesystemSettings(
        settings=FilesystemSettings(
            require_mcp_file_deletion_approval=settings.require_mcp_file_deletion_approval
        ),
        source=source,
    )


class SystemSettingsService:
    def __init__(
        self,
        overrides: SystemSettingsReader,
        writer: SystemSettingsWriter,
        defaults: SystemSettingsReader,
    ) -> None:
        self._overrides = overrides
        self._writer = writer
        self._defaults = defaults

    async def _fallback(self) -> EffectiveFilesystemSettings:
        defaults = await self._defaults.read()
        if defaults is SettingsNotConfigured.UNSET:
            return EffectiveFilesystemSettings(
                settings=FilesystemSettings(), source=SettingsSource.BUILT_IN_DEFAULT
            )
        return _filesystem_result(defaults, SettingsSource.DEPLOYMENT_DEFAULT)

    async def _effective_filesystem_settings(self) -> EffectiveFilesystemSettings:
        overrides = await self._overrides.read()
        if (
            overrides is SettingsNotConfigured.UNSET
            or "require_mcp_file_deletion_approval" not in overrides.model_fields_set
        ):
            return await self._fallback()
        return _filesystem_result(overrides, SettingsSource.ADMIN_OVERRIDE)

    async def get_effective_settings(
        self, actor_role: str
    ) -> EffectiveFilesystemSettings:
        require_administrator(actor_role)
        return await self._effective_filesystem_settings()

    async def get_settings(self, actor_role: str) -> FilesystemSettings:
        return (await self.get_effective_settings(actor_role)).settings

    async def update_settings(
        self, actor_role: str, command: UpdateSystemSettings
    ) -> FilesystemSettings:
        return (await self.set_settings(actor_role, command)).settings

    async def set_settings(
        self, actor_role: str, command: UpdateSystemSettings
    ) -> EffectiveFilesystemSettings:
        require_administrator(actor_role)
        updated = await self._writer.update(command)
        return _filesystem_result(updated, SettingsSource.ADMIN_OVERRIDE)

    async def reset_mcp_file_deletion_approval(
        self, actor_role: str
    ) -> EffectiveFilesystemSettings:
        require_administrator(actor_role)
        fallback = await self._fallback()
        await self._writer.reset_mcp_file_deletion_approval()
        return fallback

    async def _read_portable_connectors_enabled(self) -> bool:
        overrides = await self._overrides.read()
        if overrides is SettingsNotConfigured.UNSET:
            return False
        return overrides.portable_connectors_enabled

    async def allows_portable_connector_drafts(self) -> bool:
        try:
            return await self._read_portable_connectors_enabled()
        except SettingsStorageUnavailable:
            return False

    async def get_portable_connectors_enabled(self, actor_role: str) -> bool:
        require_administrator(actor_role)
        return await self._read_portable_connectors_enabled()

    async def set_portable_connectors_enabled(
        self, actor_role: str, command: UpdatePortableConnectorSettings
    ) -> bool:
        require_administrator(actor_role)
        updated = await self._writer.update(command)
        return updated.portable_connectors_enabled

    async def requires_mcp_file_deletion_approval(self) -> bool:
        try:
            settings = await self._effective_filesystem_settings()
        except SettingsStorageUnavailable:
            return DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL
        return settings.settings.require_mcp_file_deletion_approval
