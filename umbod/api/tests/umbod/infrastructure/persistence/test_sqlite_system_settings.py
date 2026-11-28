from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.support.system_settings import read_raw_settings
from umbod.core.system_settings import (
    SettingsSource,
    UpdatePortableConnectorSettings,
    UpdateSystemSettings,
    create_system_settings_service,
)

_ADMINISTRATOR = "administrator"


@pytest.mark.asyncio
async def test_sqlite_persists_settings_after_runtime_reopens(tmp_path: Path) -> None:
    database_path = tmp_path / "system-settings.sqlite"
    initial = await prepared_sqlite_runtime(database_path)
    try:
        await create_system_settings_service(initial.database).update_settings(
            _ADMINISTRATOR,
            UpdateSystemSettings(require_mcp_file_deletion_approval=False),
        )
    finally:
        await initial.shutdown()

    reopened = await prepared_sqlite_runtime(database_path)
    try:
        service = create_system_settings_service(reopened.database)
        assert await service.requires_mcp_file_deletion_approval() is False
        await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR)
    finally:
        await reopened.shutdown()

    after_reset = await prepared_sqlite_runtime(database_path)
    try:
        service = create_system_settings_service(after_reset.database)
        settings = await service.get_effective_settings(_ADMINISTRATOR)
        assert settings.source is SettingsSource.BUILT_IN_DEFAULT
        assert settings.settings.require_mcp_file_deletion_approval is True
    finally:
        await after_reset.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_sqlite_persists_explicit_portable_flag_after_runtime_reopens(
    tmp_path: Path, enabled: bool
) -> None:
    database_path = tmp_path / "system-settings.sqlite"
    initial = await prepared_sqlite_runtime(database_path)
    try:
        await create_system_settings_service(
            initial.database
        ).set_portable_connectors_enabled(
            _ADMINISTRATOR,
            UpdatePortableConnectorSettings(portable_connectors_enabled=enabled),
        )
    finally:
        await initial.shutdown()

    reopened = await prepared_sqlite_runtime(database_path)
    try:
        service = create_system_settings_service(reopened.database)
        assert await service.get_portable_connectors_enabled(_ADMINISTRATOR) is enabled
        assert await read_raw_settings(reopened.database) == [
            {"portable_connectors_enabled": enabled}
        ]
    finally:
        await reopened.shutdown()
