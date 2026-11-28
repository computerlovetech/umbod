from umbod.core.system_settings import SettingsNotConfigured, SystemSettings

from .app import AppConfig


class ConfiguredSystemSettingsDefaults:
    def __init__(self, config: AppConfig) -> None:
        self._approval = config.filesystem.require_mcp_file_deletion_approval

    async def read(self) -> SystemSettings | SettingsNotConfigured:
        if self._approval is None:
            return SettingsNotConfigured.UNSET
        return SystemSettings(require_mcp_file_deletion_approval=self._approval)
