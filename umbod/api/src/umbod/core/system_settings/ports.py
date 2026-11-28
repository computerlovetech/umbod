from enum import Enum
from typing import Protocol

from .models import SystemSettings, UpdatePortableConnectorSettings, UpdateSystemSettings


class SettingsNotConfigured(Enum):
    UNSET = "unset"


class SystemSettingsReader(Protocol):
    async def read(self) -> SystemSettings | SettingsNotConfigured: ...


class SystemSettingsWriter(Protocol):
    async def update(
        self, command: UpdateSystemSettings | UpdatePortableConnectorSettings
    ) -> SystemSettings: ...

    async def reset_mcp_file_deletion_approval(self) -> None: ...
