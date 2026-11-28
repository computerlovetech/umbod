from .errors import SettingsPermissionDenied, SettingsStorageUnavailable
from .models import (
    DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL,
    EffectiveSystemSettings,
    SettingsSource,
    SystemSettings,
    UpdateSystemSettings,
)
from .ports import SettingsNotConfigured, SystemSettingsReader, SystemSettingsWriter


def require_administrator(actor_role: str) -> None:
    if actor_role != "administrator":
        raise SettingsPermissionDenied()


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

    async def _fallback(self) -> EffectiveSystemSettings:
        defaults = await self._defaults.read()
        if defaults is SettingsNotConfigured.UNSET:
            return EffectiveSystemSettings(
                settings=SystemSettings(), source=SettingsSource.BUILT_IN_DEFAULT
            )
        return EffectiveSystemSettings(
            settings=defaults, source=SettingsSource.DEPLOYMENT_DEFAULT
        )

    async def _effective_settings(self) -> EffectiveSystemSettings:
        overrides = await self._overrides.read()
        if overrides is SettingsNotConfigured.UNSET:
            return await self._fallback()
        return EffectiveSystemSettings(
            settings=overrides, source=SettingsSource.ADMIN_OVERRIDE
        )

    async def get_effective_settings(self, actor_role: str) -> EffectiveSystemSettings:
        require_administrator(actor_role)
        return await self._effective_settings()

    async def get_settings(self, actor_role: str) -> SystemSettings:
        return (await self.get_effective_settings(actor_role)).settings

    async def update_settings(
        self, actor_role: str, command: UpdateSystemSettings
    ) -> SystemSettings:
        return (await self.set_settings(actor_role, command)).settings

    async def set_settings(
        self, actor_role: str, command: UpdateSystemSettings
    ) -> EffectiveSystemSettings:
        require_administrator(actor_role)
        updated = await self._writer.update(command)
        return EffectiveSystemSettings(
            settings=updated, source=SettingsSource.ADMIN_OVERRIDE
        )

    async def reset_mcp_file_deletion_approval(
        self, actor_role: str
    ) -> EffectiveSystemSettings:
        require_administrator(actor_role)
        fallback = await self._fallback()
        await self._writer.reset_mcp_file_deletion_approval()
        return fallback

    async def requires_mcp_file_deletion_approval(self) -> bool:
        try:
            settings = await self._effective_settings()
        except SettingsStorageUnavailable:
            return DEFAULT_REQUIRE_MCP_FILE_DELETION_APPROVAL
        return settings.settings.require_mcp_file_deletion_approval
