from types import MappingProxyType

from umbod.core.callers.membership import (
    INHERITED_GROUP_MEMBERSHIP,
    UNAVAILABLE_GROUP_MEMBERSHIP,
    GroupMembershipResolver,
    ProviderGroupOverrides,
    ProviderMembershipClaim,
)
from umbod.core.groups.stores.reads import read_registered_group_ids
from umbod.core.persistence import Database
from umbod.core.system_settings import SettingsNotConfigured, SettingsStorageUnavailable
from umbod.core.system_settings.provider_group_mappings import read_saved_provider_group_mappings

from .app import AppConfig


def _configured_provider_membership_claim(
    config: AppConfig,
) -> ProviderMembershipClaim | SettingsNotConfigured:
    issuer = config.oidc.issuer_url
    claim = config.mcp.permission_group_claim
    if config.mcp.auth_mode != "oidc" or not issuer.strip() or not claim.strip():
        return SettingsNotConfigured.UNSET
    return ProviderMembershipClaim(issuer=issuer, claim=claim)


class ConfiguredGroupMembershipSource:
    def __init__(self, config: AppConfig, database: Database) -> None:
        self._database = database
        self._provider_claim = _configured_provider_membership_claim(config)

    async def capture(self) -> GroupMembershipResolver:
        provider_claim = self._provider_claim
        if provider_claim is SettingsNotConfigured.UNSET:
            return INHERITED_GROUP_MEMBERSHIP
        try:
            async with self._database.read_session() as session:
                mappings = await read_saved_provider_group_mappings(session)
                if mappings is SettingsNotConfigured.UNSET or not mappings:
                    return INHERITED_GROUP_MEMBERSHIP
                registered = await read_registered_group_ids(session)
        except Exception:
            return UNAVAILABLE_GROUP_MEMBERSHIP
        targets_by_value: dict[str, list[str]] = {}
        for mapping in mappings:
            if mapping.group_id in registered:
                targets_by_value.setdefault(mapping.external_value, []).append(mapping.group_id)
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
                mappings = await read_saved_provider_group_mappings(session)
                if mappings is SettingsNotConfigured.UNSET:
                    return frozenset()
                return frozenset(mapping.group_id for mapping in mappings)
        except Exception:
            raise SettingsStorageUnavailable() from None
