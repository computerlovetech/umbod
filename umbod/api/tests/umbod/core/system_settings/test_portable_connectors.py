from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from tests.support.system_settings import read_raw_settings, save_raw_settings
from umbod.core.persistence import Database, DatabaseSession, TransactionMode
from umbod.core.system_settings import (
    SettingsStorageUnavailable,
    UpdatePortableConnectorSettings,
    create_system_settings_service,
)

_ADMINISTRATOR = "administrator"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [{}, {"require_mcp_file_deletion_approval": False}])
async def test_legacy_documents_default_to_off_without_write(
    database: Database, legacy: dict[str, bool]
) -> None:
    await save_raw_settings(database, legacy)

    service = create_system_settings_service(database)
    assert await service.get_portable_connectors_enabled(_ADMINISTRATOR) is False
    assert await read_raw_settings(database) == [legacy]


@pytest.mark.asyncio
async def test_draft_policy_reads_current_flag_without_administrator_role(
    database: Database,
) -> None:
    controller = create_system_settings_service(database)
    policy = create_system_settings_service(database)

    assert await policy.allows_portable_connector_drafts() is False

    for enabled in (True, False):
        await controller.set_portable_connectors_enabled(
            _ADMINISTRATOR,
            UpdatePortableConnectorSettings(portable_connectors_enabled=enabled),
        )
        assert await policy.allows_portable_connector_drafts() is enabled


@pytest.mark.asyncio
async def test_draft_policy_fails_closed_when_settings_cannot_be_read(
    database: Database,
) -> None:
    await save_raw_settings(database, {"portable_connectors_enabled": "true"})
    service = create_system_settings_service(database)

    assert await service.allows_portable_connector_drafts() is False
    with pytest.raises(SettingsStorageUnavailable):
        await service.get_portable_connectors_enabled(_ADMINISTRATOR)


@pytest.mark.asyncio
async def test_filesystem_settings_results_describe_only_approval(
    database: Database,
) -> None:
    service = create_system_settings_service(database)
    await service.set_portable_connectors_enabled(
        _ADMINISTRATOR,
        UpdatePortableConnectorSettings(portable_connectors_enabled=True),
    )

    current = await service.get_settings(_ADMINISTRATOR)
    reset = await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR)

    assert current.model_dump() == {"require_mcp_file_deletion_approval": True}
    assert reset.settings == current
    assert await service.get_portable_connectors_enabled(_ADMINISTRATOR) is True


@pytest.mark.asyncio
async def test_failed_flag_update_does_not_report_success_or_change_stored_value(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = create_system_settings_service(database)
    await service.set_portable_connectors_enabled(
        _ADMINISTRATOR,
        UpdatePortableConnectorSettings(portable_connectors_enabled=False),
    )
    original_session = database.session

    @asynccontextmanager
    async def interrupt_write(
        *, mode: TransactionMode
    ) -> AsyncIterator[DatabaseSession]:
        assert mode is TransactionMode.SERIALIZED_WRITE
        async with original_session(mode=mode) as session:
            yield session
            raise OSError()

    monkeypatch.setattr(database, "session", interrupt_write)

    with pytest.raises(SettingsStorageUnavailable):
        await service.set_portable_connectors_enabled(
            _ADMINISTRATOR,
            UpdatePortableConnectorSettings(portable_connectors_enabled=True),
        )

    assert await service.get_portable_connectors_enabled(_ADMINISTRATOR) is False
    assert await read_raw_settings(database) == [{"portable_connectors_enabled": False}]
