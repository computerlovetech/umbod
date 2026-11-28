from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.config import AppConfig
from umbod.config.system_settings import ConfiguredProviderGroupMappingsDefaults
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import Database
from umbod.core.system_settings import (
    SettingsNotConfigured,
    SettingsSource,
    UpdateSystemSettings,
    create_system_settings_service,
)
from umbod.core.system_settings.provider_group_mappings import (
    ProviderGroupMapping,
    ProviderGroupMappingsService,
    create_provider_group_mappings_service,
)

_ADMINISTRATOR = "administrator"
_DEFAULT = (
    '[{"external_value":"test","group_id":"future"}]'
)


def _mappings_service(
    database: Database, defaults: ConfiguredProviderGroupMappingsDefaults,
) -> ProviderGroupMappingsService:
    return create_provider_group_mappings_service(
        database, defaults, SettingsNotConfigured.UNSET
    )


@asynccontextmanager
async def _open_database(path: Path) -> AsyncIterator[Database]:
    runtime = await prepared_sqlite_runtime(path)
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_sqlite_persists_empty_override_and_reset_independently_of_approval(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.sqlite"
    defaults = ConfiguredProviderGroupMappingsDefaults(
        AppConfig(provider_group_overrides=_DEFAULT)
    )

    async with _open_database(path) as database:
        mappings = _mappings_service(database, defaults)
        approval = create_system_settings_service(database)
        deployment = await mappings.get(_ADMINISTRATOR)
        assert deployment.source is SettingsSource.DEPLOYMENT_DEFAULT
        assert deployment.mappings[0].group_id == "future"

        saved_mappings = await mappings.replace(_ADMINISTRATOR, ())
        saved_approval = await approval.set_settings(
            _ADMINISTRATOR,
            UpdateSystemSettings(require_mcp_file_deletion_approval=False),
        )
        assert await mappings.get(_ADMINISTRATOR) == saved_mappings

    async with _open_database(path) as database:
        mappings = _mappings_service(database, defaults)
        approval = create_system_settings_service(database)
        assert await mappings.get(_ADMINISTRATOR) == saved_mappings

        assert await mappings.reset(_ADMINISTRATOR) == deployment
        assert await approval.get_effective_settings(_ADMINISTRATOR) == saved_approval

    async with _open_database(path) as database:
        mappings = _mappings_service(database, defaults)
        assert await mappings.get(_ADMINISTRATOR) == deployment


@pytest.mark.asyncio
async def test_sqlite_persists_whole_list_replacement_after_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.sqlite"
    defaults = ConfiguredProviderGroupMappingsDefaults(AppConfig())
    first = ProviderGroupMapping(
        external_value="external", group_id="accepted"
    )
    second = ProviderGroupMapping(
        external_value="another-external", group_id="accepted"
    )
    async with _open_database(path) as database:
        await create_group_management(database).register_group(
            RegisterGroup(group_id="accepted")
        )
        mappings = _mappings_service(database, defaults)

        await mappings.replace(_ADMINISTRATOR, (first,))
        saved = await mappings.replace(_ADMINISTRATOR, (second, first))

    async with _open_database(path) as database:
        mappings = _mappings_service(database, defaults)
        assert await mappings.get(_ADMINISTRATOR) == saved
        assert saved.mappings == (second, first)
