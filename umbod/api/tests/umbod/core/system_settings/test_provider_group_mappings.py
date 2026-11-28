import pytest

from umbod.core.callers.membership import ProviderMembershipClaim
from umbod.core.system_settings import (
    SettingsNotConfigured,
    SettingsSource,
    SettingsStorageUnavailable,
)
from umbod.core.system_settings.provider_group_mappings import (
    ProviderGroupMapping,
    ProviderGroupMappings,
    ProviderGroupMappingsService,
)

_ADMINISTRATOR = "administrator"
_GROUP_ID = "team"
_PROVIDER_CLAIM = ProviderMembershipClaim(issuer="https://issuer.example/", claim="groups")
_INHERITED_RULE = ProviderGroupMapping(
    external_value=_GROUP_ID,
    group_id=_GROUP_ID,
)


class MemoryMappings:
    def __init__(self, settings: ProviderGroupMappings | SettingsNotConfigured) -> None:
        self._settings = settings

    async def read(self) -> ProviderGroupMappings | SettingsNotConfigured:
        return self._settings

    async def registered_group_ids(self) -> frozenset[str]:
        return frozenset({_GROUP_ID, "\u001c"})

    async def replace(self, mappings: ProviderGroupMappings) -> None:
        self._settings = mappings

    async def reset(self) -> None:
        self._settings = SettingsNotConfigured.UNSET


class UnavailableMappings(MemoryMappings):
    async def read(self) -> ProviderGroupMappings:
        raise SettingsStorageUnavailable()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_claim", "initial_source", "initial_mappings"),
    [
        (SettingsNotConfigured.UNSET, SettingsSource.BUILT_IN_DEFAULT, ()),
        (_PROVIDER_CLAIM, "inherited_claim_default", (_INHERITED_RULE,)),
    ],
)
async def test_saved_empty_list_is_distinct_from_idempotent_reset(
    provider_claim: ProviderMembershipClaim | SettingsNotConfigured,
    initial_source: str,
    initial_mappings: ProviderGroupMappings,
) -> None:
    service = ProviderGroupMappingsService(
        MemoryMappings(SettingsNotConfigured.UNSET),
        provider_claim,
    )
    initial = await service.get(_ADMINISTRATOR)
    assert initial.mappings == initial_mappings
    assert initial.source == initial_source

    saved = await service.replace(_ADMINISTRATOR, ())
    assert saved.mappings == ()
    assert saved.source is SettingsSource.ADMIN_OVERRIDE
    assert await service.get(_ADMINISTRATOR) == saved

    assert await service.reset(_ADMINISTRATOR) == initial
    assert await service.reset(_ADMINISTRATOR) == initial
    assert await service.get(_ADMINISTRATOR) == initial


@pytest.mark.asyncio
async def test_storage_failure_is_not_an_unset_override() -> None:
    service = ProviderGroupMappingsService(
        UnavailableMappings(SettingsNotConfigured.UNSET),
        SettingsNotConfigured.UNSET,
    )
    with pytest.raises(SettingsStorageUnavailable):
        await service.get(_ADMINISTRATOR)
