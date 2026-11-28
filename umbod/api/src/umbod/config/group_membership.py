from types import MappingProxyType

from umbod.core.callers.membership import (
    INHERITED_GROUP_MEMBERSHIP,
    UNAVAILABLE_GROUP_MEMBERSHIP,
    GroupMembershipResolver,
    ProviderGroupOverrides,
)
from umbod.core.groups.stores.reads import read_registered_group_ids
from umbod.core.persistence import Database, ReadSession
from umbod.core.system_settings import SettingsNotConfigured, SettingsStorageUnavailable
from umbod.core.system_settings.provider_group_mappings import (
    ProviderGroupMappings,
    read_saved_provider_group_mappings,
)

from .app import AppConfig
from .system_settings import (
    ConfiguredProviderGroupMappingsDefaults,
    configured_provider_membership_claim,
)


def _target_group_ids(mappings: ProviderGroupMappings) -> frozenset[str]:
    return frozenset(mapping.group_id for mapping in mappings)


class ConfiguredGroupMembershipSource:
    def __init__(self, config: AppConfig, database: Database) -> None:
        self._database = database
        self._defaults = ConfiguredProviderGroupMappingsDefaults(config)
        self._provider_claim = configured_provider_membership_claim(config)

    async def _read_live_mappings(self, session: ReadSession) -> ProviderGroupMappings:
        override = await read_saved_provider_group_mappings(session)
        if override is not SettingsNotConfigured.UNSET:
            return override
        return self._defaults.read_mappings()

    async def capture(self) -> GroupMembershipResolver:
        provider_claim = self._provider_claim
        if provider_claim is SettingsNotConfigured.UNSET:
            return INHERITED_GROUP_MEMBERSHIP
        try:
            async with self._database.read_session() as session:
                mappings = await self._read_live_mappings(session)
                if not mappings:
                    return INHERITED_GROUP_MEMBERSHIP
                registered = await read_registered_group_ids(session)
        except Exception:
            return UNAVAILABLE_GROUP_MEMBERSHIP
        targets_by_value: dict[str, list[str]] = {}
        for mapping in mappings:
            targets = targets_by_value.setdefault(mapping.external_value, [])
            if mapping.group_id in registered:
                targets.append(mapping.group_id)
        return GroupMembershipResolver(
            ProviderGroupOverrides(
                provider_claim=provider_claim,
                targets_by_value=MappingProxyType({
                    value: tuple(targets) for value, targets in targets_by_value.items()
                }),
            )
        )

    async def target_group_ids(self) -> frozenset[str]:
        try:
            async with self._database.read_session() as session:
                return _target_group_ids(await self._read_live_mappings(session))
        except Exception:
            raise SettingsStorageUnavailable() from None
