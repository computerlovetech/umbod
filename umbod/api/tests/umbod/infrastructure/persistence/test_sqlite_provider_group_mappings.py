from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import Database
from umbod.core.system_settings import (
    SettingsSource,
    UpdateSystemSettings,
    create_system_settings_service,
)
from umbod.core.system_settings.provider_group_mappings import (
    ProviderGroupMapping,
    create_provider_group_mappings_service,
)

_ADMINISTRATOR = "administrator"


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
    async with _open_database(path) as database:
        mappings = create_provider_group_mappings_service(database)
        approval = create_system_settings_service(database)
        default = await mappings.get(_ADMINISTRATOR)
        assert default.source is SettingsSource.BUILT_IN_DEFAULT
        assert default.mappings == ()

        saved_mappings = await mappings.replace(_ADMINISTRATOR, ())
        assert saved_mappings.source is SettingsSource.ADMIN_OVERRIDE
        saved_approval = await approval.set_settings(
            _ADMINISTRATOR,
            UpdateSystemSettings(require_mcp_file_deletion_approval=False),
        )
        assert await mappings.get(_ADMINISTRATOR) == saved_mappings

    async with _open_database(path) as database:
        mappings = create_provider_group_mappings_service(database)
        approval = create_system_settings_service(database)
        assert await mappings.get(_ADMINISTRATOR) == saved_mappings

        assert await mappings.reset(_ADMINISTRATOR) == default
        assert await approval.get_effective_settings(_ADMINISTRATOR) == saved_approval

    async with _open_database(path) as database:
        mappings = create_provider_group_mappings_service(database)
        assert await mappings.get(_ADMINISTRATOR) == default


@pytest.mark.asyncio
async def test_sqlite_persists_whole_list_replacement_after_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.sqlite"
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
        mappings = create_provider_group_mappings_service(database)

        await mappings.replace(_ADMINISTRATOR, (first,))
        saved = await mappings.replace(_ADMINISTRATOR, (second, first))

    async with _open_database(path) as database:
        mappings = create_provider_group_mappings_service(database)
        assert await mappings.get(_ADMINISTRATOR) == saved
        assert saved.mappings == (second, first)
