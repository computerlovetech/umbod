from typing import Protocol

from ..ports import SettingsNotConfigured
from .models import EffectiveProviderGroupMappings, ProviderGroupMappings


class ProviderGroupMappingsReader(Protocol):
    async def read(self) -> EffectiveProviderGroupMappings | SettingsNotConfigured: ...


class ProviderGroupMappingsStore(Protocol):
    async def read(self) -> ProviderGroupMappings | SettingsNotConfigured: ...

    async def registered_group_ids(self) -> frozenset[str]: ...

    async def replace(self, mappings: ProviderGroupMappings) -> None: ...

    async def reset(self) -> None: ...
