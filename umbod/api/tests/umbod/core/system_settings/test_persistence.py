import pytest

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.system_settings import read_raw_settings, save_raw_settings
from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered
from umbod.core.system_settings import (
    SettingsNotConfigured,
    SettingsSource,
    SettingsStorageUnavailable,
    UpdateSystemSettings,
    create_system_settings_service,
)
from umbod.core.system_settings.schema import SYSTEM_SETTINGS_TABLE
from umbod.core.system_settings.store import DatabaseSystemSettingsStore

_ADMINISTRATOR = "administrator"


@pytest.mark.asyncio
async def test_absent_settings_require_approval_without_creating_a_row(
    database: Database,
) -> None:
    service = create_system_settings_service(database)

    assert (
        await service.get_settings(_ADMINISTRATOR)
    ).require_mcp_file_deletion_approval is True
    assert await service.requires_mcp_file_deletion_approval() is True
    async with database.read_session() as session:
        assert not await session.find_many(
            SYSTEM_SETTINGS_TABLE, Query(NoFilter(), AllFields(), Unordered())
        )


@pytest.mark.asyncio
async def test_valid_document_without_approval_field_requires_approval(
    database: Database,
) -> None:
    await save_raw_settings(database, {})
    service = create_system_settings_service(database)

    assert (
        await DatabaseSystemSettingsStore(database).read()
        is SettingsNotConfigured.UNSET
    )

    assert (
        await service.get_settings(_ADMINISTRATOR)
    ).require_mcp_file_deletion_approval is True
    assert await service.requires_mcp_file_deletion_approval() is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial", [None, {}, {"require_mcp_file_deletion_approval": False}]
)
async def test_reset_is_idempotent_and_leaves_no_settings_row(
    database: Database,
    initial: object,
) -> None:
    if initial is not None:
        await save_raw_settings(database, initial)
    service = create_system_settings_service(database)

    reset = await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR)
    assert await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR) == reset

    assert reset.source is SettingsSource.BUILT_IN_DEFAULT
    assert (
        await DatabaseSystemSettingsStore(database).read()
        is SettingsNotConfigured.UNSET
    )
    async with database.read_session() as session:
        assert not await session.find_many(
            SYSTEM_SETTINGS_TABLE, Query(NoFilter(), AllFields(), Unordered())
        )


@pytest.mark.asyncio
async def test_updates_share_a_single_row_across_services(database: Database) -> None:
    writer = create_system_settings_service(database)

    disabled = await writer.update_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=False)
    )
    reader = create_system_settings_service(database)
    assert disabled.require_mcp_file_deletion_approval is False
    assert await reader.requires_mcp_file_deletion_approval() is False

    enabled = await writer.update_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=True)
    )

    assert await reader.get_settings(_ADMINISTRATOR) == enabled
    assert await reader.requires_mcp_file_deletion_approval() is True
    async with database.read_session() as session:
        rows = await session.find_many(
            SYSTEM_SETTINGS_TABLE, Query(NoFilter(), AllFields(), Unordered())
        )
    assert [row.singleton for row in rows] == [1]


@pytest.mark.asyncio
async def test_independent_in_memory_databases_do_not_share_settings(
    database: Database,
) -> None:
    writer = create_system_settings_service(database)
    await writer.update_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=False)
    )
    isolated = await prepared_inmemory_runtime()
    try:
        assert (
            await create_system_settings_service(
                isolated.database
            ).requires_mcp_file_deletion_approval()
            is True
        )
    finally:
        await isolated.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "not a settings object",
        {"require_mcp_file_deletion_approval": "false"},
        {"require_mcp_file_deletion_approval": 0},
        {"require_mcp_file_deletion_approval": None},
        {"require_mcp_file_deletion_approval": False, "unknown": False},
    ],
)
async def test_invalid_stored_document_fails_closed_and_cannot_be_overwritten(
    database: Database, payload: object
) -> None:
    service = create_system_settings_service(database)
    await service.update_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=False)
    )
    assert await service.requires_mcp_file_deletion_approval() is False
    await save_raw_settings(database, payload)

    assert await service.requires_mcp_file_deletion_approval() is True
    with pytest.raises(SettingsStorageUnavailable):
        await service.get_settings(_ADMINISTRATOR)
    with pytest.raises(SettingsStorageUnavailable):
        await service.update_settings(
            _ADMINISTRATOR,
            UpdateSystemSettings(require_mcp_file_deletion_approval=True),
        )

    with pytest.raises(SettingsStorageUnavailable):
        await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR)

    assert await read_raw_settings(database) == [payload]
