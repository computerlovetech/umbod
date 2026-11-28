from pydantic import ValidationError

from umbod.core.callers.membership import ProviderMembershipClaim

from ..errors import SettingsStorageUnavailable
from ..models import SettingsSource
from ..ports import SettingsNotConfigured
from ..service import require_administrator
from .models import (
    EffectiveProviderGroupMappings,
    ProviderGroupMapping,
    ProviderGroupMappings,
    is_mappable_group_id,
)
from .ports import ProviderGroupMappingsReader, ProviderGroupMappingsStore


class ProviderGroupMappingsService:
    def __init__(
        self,
        store: ProviderGroupMappingsStore,
        defaults: ProviderGroupMappingsReader,
        provider_claim: ProviderMembershipClaim | SettingsNotConfigured,
    ) -> None:
        self._store = store
        self._defaults = defaults
        self._provider_claim = provider_claim

    async def _fallback(self) -> EffectiveProviderGroupMappings:
        defaults = await self._defaults.read()
        if defaults is not SettingsNotConfigured.UNSET:
            return defaults
        if self._provider_claim is SettingsNotConfigured.UNSET:
            return EffectiveProviderGroupMappings(
                mappings=(), source=SettingsSource.BUILT_IN_DEFAULT
            )
        group_ids = await self._store.registered_group_ids()
        try:
            mappings = tuple(
                ProviderGroupMapping(
                    external_value=group_id,
                    group_id=group_id,
                )
                for group_id in sorted(group_ids)
                if is_mappable_group_id(group_id)
            )
        except ValidationError:
            raise SettingsStorageUnavailable() from None
        return EffectiveProviderGroupMappings(
            mappings=mappings, source="inherited_claim_default"
        )

    async def get(self, actor_role: str) -> EffectiveProviderGroupMappings:
        require_administrator(actor_role)
        override = await self._store.read()
        if override is SettingsNotConfigured.UNSET:
            return await self._fallback()
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
        fallback = await self._fallback()
        await self._store.reset()
        return fallback
