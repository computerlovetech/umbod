from pydantic import TypeAdapter, ValidationError

from umbod.core.callers.membership import ProviderMembershipClaim

from umbod.core.system_settings import (
    SettingsNotConfigured,
    SettingsSource,
    SettingsStorageUnavailable,
    SystemSettings,
)
from umbod.core.system_settings.provider_group_mappings import (
    EffectiveProviderGroupMappings,
    ProviderGroupMappings,
)

from .app import AppConfig


class ConfiguredSystemSettingsDefaults:
    def __init__(self, config: AppConfig) -> None:
        self._approval = config.filesystem.require_mcp_file_deletion_approval

    async def read(self) -> SystemSettings | SettingsNotConfigured:
        if self._approval is None:
            return SettingsNotConfigured.UNSET
        return SystemSettings(require_mcp_file_deletion_approval=self._approval)


_PROVIDER_GROUP_MAPPINGS_ADAPTER: TypeAdapter[ProviderGroupMappings] = TypeAdapter(
    ProviderGroupMappings
)


def parse_provider_group_mappings(raw: str) -> ProviderGroupMappings:
    return _PROVIDER_GROUP_MAPPINGS_ADAPTER.validate_json(raw)


def configured_provider_membership_claim(
    config: AppConfig,
) -> ProviderMembershipClaim | SettingsNotConfigured:
    issuer = config.oidc.issuer_url
    claim = config.mcp.permission_group_claim
    if config.mcp.auth_mode != "oidc" or not issuer.strip() or not claim.strip():
        return SettingsNotConfigured.UNSET
    return ProviderMembershipClaim(issuer=issuer, claim=claim)


def _parse_configured_mappings(raw: str) -> ProviderGroupMappings:
    try:
        return parse_provider_group_mappings(raw)
    except ValidationError:
        raise SettingsStorageUnavailable() from None


class ConfiguredProviderGroupMappingsDefaults:
    def __init__(self, config: AppConfig) -> None:
        self._published = config.provider_group_overrides

    async def read(self) -> EffectiveProviderGroupMappings | SettingsNotConfigured:
        if self._published is None:
            return SettingsNotConfigured.UNSET
        return EffectiveProviderGroupMappings(
            mappings=self.read_mappings(),
            source=SettingsSource.DEPLOYMENT_DEFAULT,
        )

    def read_mappings(self) -> ProviderGroupMappings:
        if self._published is None:
            return ()
        return _parse_configured_mappings(self._published)
