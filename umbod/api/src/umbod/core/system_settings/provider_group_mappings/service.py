from typing import Final

from ..models import SettingsSource
from ..ports import SettingsNotConfigured
from ..service import require_administrator
from .models import EffectiveProviderGroupMappings, ProviderGroupMappings
from .ports import ProviderGroupMappingsStore

_EMPTY_MAPPINGS: Final = EffectiveProviderGroupMappings(
    mappings=(), source=SettingsSource.BUILT_IN_DEFAULT
)


class ProviderGroupMappingsService:
    def __init__(self, store: ProviderGroupMappingsStore) -> None:
        self._store = store

    async def get(self, actor_role: str) -> EffectiveProviderGroupMappings:
        require_administrator(actor_role)
        override = await self._store.read()
        if override is SettingsNotConfigured.UNSET:
            return _EMPTY_MAPPINGS
        return EffectiveProviderGroupMappings(
            mappings=override,
            source=SettingsSource.ADMIN_OVERRIDE,
        )

    async def replace(
        self, actor_role: str, mappings: ProviderGroupMappings
    ) -> EffectiveProviderGroupMappings:
        require_administrator(actor_role)
        await self._store.replace(mappings)
        return EffectiveProviderGroupMappings(
            mappings=mappings, source=SettingsSource.ADMIN_OVERRIDE
        )

    async def reset(self, actor_role: str) -> EffectiveProviderGroupMappings:
        require_administrator(actor_role)
        await self._store.reset()
        return _EMPTY_MAPPINGS
