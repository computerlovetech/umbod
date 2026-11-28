import pytest

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
_RULE = ProviderGroupMapping(
    external_value="staff",
    group_id=_GROUP_ID,
)


class MemoryMappings:
    def __init__(self, settings: ProviderGroupMappings | SettingsNotConfigured) -> None:
        self._settings = settings

    async def read(self) -> ProviderGroupMappings | SettingsNotConfigured:
        return self._settings

    async def replace(self, mappings: ProviderGroupMappings) -> None:
        self._settings = mappings

    async def reset(self) -> None:
        self._settings = SettingsNotConfigured.UNSET


class UnavailableMappings(MemoryMappings):
    async def read(self) -> ProviderGroupMappings:
        raise SettingsStorageUnavailable()


@pytest.mark.asyncio
@pytest.mark.parametrize("mappings", [(), (_RULE,)])
async def test_save_and_idempotent_reset(mappings: ProviderGroupMappings) -> None:
    service = ProviderGroupMappingsService(MemoryMappings(SettingsNotConfigured.UNSET))
    initial = await service.get(_ADMINISTRATOR)
    assert initial.mappings == ()
    assert initial.source is SettingsSource.BUILT_IN_DEFAULT

    saved = await service.replace(_ADMINISTRATOR, mappings)
    assert saved.mappings == mappings
    assert saved.source is SettingsSource.ADMIN_OVERRIDE
    assert await service.get(_ADMINISTRATOR) == saved

    assert await service.reset(_ADMINISTRATOR) == initial
    assert await service.reset(_ADMINISTRATOR) == initial
    assert await service.get(_ADMINISTRATOR) == initial


@pytest.mark.asyncio
async def test_storage_failure_is_not_an_unset_override() -> None:
    service = ProviderGroupMappingsService(UnavailableMappings(SettingsNotConfigured.UNSET))
    with pytest.raises(SettingsStorageUnavailable):
        await service.get(_ADMINISTRATOR)
