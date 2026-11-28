import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from pydantic import ValidationError

from umbod.core.persistence import (
    Database,
    DatabaseSession,
    ReadSession,
    TransactionMode,
)
from umbod.core.system_settings import (
    SettingsPermissionDenied,
    SettingsSource,
    SettingsStorageUnavailable,
    SystemSettings,
    UpdatePortableConnectorSettings,
    UpdateSystemSettings,
    create_system_settings_service,
    create_system_settings_service_with_defaults,
)

_ADMINISTRATOR = "administrator"


class _FixedDefaultsReader:
    def __init__(self, require_approval: bool) -> None:
        self._settings = SystemSettings(
            require_mcp_file_deletion_approval=require_approval
        )

    async def read(self) -> SystemSettings:
        return self._settings


@pytest.mark.asyncio
@pytest.mark.parametrize("require_approval", [False, True])
async def test_saved_override_takes_precedence_over_read_only_defaults(
    database: Database,
    require_approval: bool,
) -> None:
    service = create_system_settings_service_with_defaults(
        database,
        defaults=_FixedDefaultsReader(require_approval),
    )

    assert await service.requires_mcp_file_deletion_approval() is require_approval
    assert (
        await service.get_settings(_ADMINISTRATOR)
    ).require_mcp_file_deletion_approval is require_approval

    override = UpdateSystemSettings(
        require_mcp_file_deletion_approval=not require_approval
    )
    await service.update_settings(_ADMINISTRATOR, override)

    assert await service.requires_mcp_file_deletion_approval() is not require_approval
    assert (
        await service.get_settings(_ADMINISTRATOR)
    ).require_mcp_file_deletion_approval is not require_approval


@pytest.mark.asyncio
async def test_override_equal_to_default_has_its_own_source(database: Database) -> None:
    service = create_system_settings_service_with_defaults(
        database, defaults=_FixedDefaultsReader(True)
    )
    assert (
        await service.get_effective_settings(_ADMINISTRATOR)
    ).source is SettingsSource.DEPLOYMENT_DEFAULT

    saved = await service.set_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=True)
    )

    assert saved.source is SettingsSource.ADMIN_OVERRIDE
    assert await service.get_effective_settings(_ADMINISTRATOR) == saved


class _UnavailableDefaultsReader:
    async def read(self) -> SystemSettings:
        raise SettingsStorageUnavailable()


@pytest.mark.asyncio
async def test_unavailable_defaults_require_approval_without_an_override(
    database: Database,
) -> None:
    service = create_system_settings_service_with_defaults(
        database,
        defaults=_UnavailableDefaultsReader(),
    )

    assert await service.requires_mcp_file_deletion_approval() is True
    with pytest.raises(SettingsStorageUnavailable):
        await service.get_settings(_ADMINISTRATOR)


@pytest.mark.asyncio
async def test_reset_leaves_override_intact_when_fallback_cannot_be_resolved(
    database: Database,
) -> None:
    service = create_system_settings_service_with_defaults(
        database, defaults=_UnavailableDefaultsReader()
    )
    saved = await service.set_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=False)
    )

    with pytest.raises(SettingsStorageUnavailable):
        await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR)

    assert await service.get_effective_settings(_ADMINISTRATOR) == saved


@pytest.mark.asyncio
async def test_mutations_return_effective_settings_without_a_separate_read(
    database: Database, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_read() -> ReadSession:
        pytest.fail("Mutations must not reread the settings after committing")

    monkeypatch.setattr(database, "read_session", reject_read)
    service = create_system_settings_service_with_defaults(
        database, defaults=_FixedDefaultsReader(False)
    )

    saved = await service.set_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=True)
    )
    reset = await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR)

    assert saved.source is SettingsSource.ADMIN_OVERRIDE
    assert saved.settings.require_mcp_file_deletion_approval is True
    assert reset.source is SettingsSource.DEPLOYMENT_DEFAULT
    assert reset.settings.require_mcp_file_deletion_approval is False


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "Administrator", ""])
async def test_management_rejects_non_administrators_before_storage_access(
    database: Database, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    def reject_read() -> ReadSession:
        pytest.fail("Unauthorized read opened a session")

    def reject_write(*, mode: TransactionMode) -> DatabaseSession:
        pytest.fail("Unauthorized update opened a session")

    monkeypatch.setattr(database, "read_session", reject_read)
    monkeypatch.setattr(database, "session", reject_write)
    service = create_system_settings_service(database)

    with pytest.raises(SettingsPermissionDenied):
        await service.get_settings(role)
    with pytest.raises(SettingsPermissionDenied):
        await service.update_settings(
            role, UpdateSystemSettings(require_mcp_file_deletion_approval=False)
        )
    with pytest.raises(SettingsPermissionDenied):
        await service.reset_mcp_file_deletion_approval(role)
    with pytest.raises(SettingsPermissionDenied):
        await service.get_portable_connectors_enabled(role)
    with pytest.raises(SettingsPermissionDenied):
        await service.set_portable_connectors_enabled(
            role, UpdatePortableConnectorSettings(portable_connectors_enabled=True)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"require_mcp_file_deletion_approval": None},
        {"require_mcp_file_deletion_approval": "false"},
        {"require_mcp_file_deletion_approval": 0},
        {"require_mcp_file_deletion_approval": False, "unexpected": True},
    ],
)
async def test_invalid_update_leaves_persisted_settings_unchanged(
    database: Database, payload: dict[str, object]
) -> None:
    service = create_system_settings_service(database)
    previous = await service.update_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=True)
    )

    with pytest.raises(ValidationError):
        await service.update_settings(
            _ADMINISTRATOR, UpdateSystemSettings.model_validate(payload)
        )

    assert await service.get_settings(_ADMINISTRATOR) == previous


@pytest.mark.asyncio
async def test_read_failure_requires_approval_even_with_permissive_defaults(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = create_system_settings_service_with_defaults(
        database,
        defaults=_FixedDefaultsReader(False),
    )
    await service.update_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=False)
    )
    assert await service.requires_mcp_file_deletion_approval() is False

    def fail_read() -> ReadSession:
        raise OSError("Private database connection information")

    monkeypatch.setattr(database, "read_session", fail_read)

    assert await service.requires_mcp_file_deletion_approval() is True
    with pytest.raises(
        SettingsStorageUnavailable, match="^System settings storage is unavailable$"
    ):
        await service.get_settings(_ADMINISTRATOR)


@pytest.mark.asyncio
async def test_read_cancellation_propagates_through_policy_lookup(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    def cancel_read() -> ReadSession:
        raise asyncio.CancelledError()

    monkeypatch.setattr(database, "read_session", cancel_read)
    service = create_system_settings_service(database)

    with pytest.raises(asyncio.CancelledError):
        await service.requires_mcp_file_deletion_approval()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transaction_error", "expected_error"),
    [
        (OSError, SettingsStorageUnavailable),
        (asyncio.CancelledError, asyncio.CancelledError),
    ],
)
@pytest.mark.parametrize("operation", ["set", "reset"])
async def test_failed_write_transaction_rolls_back_without_reporting_success(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    transaction_error: type[BaseException],
    expected_error: type[BaseException],
    operation: str,
) -> None:
    service = create_system_settings_service(database)
    saved = await service.set_settings(
        _ADMINISTRATOR, UpdateSystemSettings(require_mcp_file_deletion_approval=False)
    )
    original_session = database.session

    @asynccontextmanager
    async def interrupt_write(
        *, mode: TransactionMode
    ) -> AsyncIterator[DatabaseSession]:
        assert mode is TransactionMode.SERIALIZED_WRITE
        async with original_session(mode=mode) as session:
            yield session
            raise transaction_error()

    monkeypatch.setattr(database, "session", interrupt_write)

    with pytest.raises(expected_error):
        if operation == "reset":
            await service.reset_mcp_file_deletion_approval(_ADMINISTRATOR)
        else:
            await service.set_settings(
                _ADMINISTRATOR,
                UpdateSystemSettings(require_mcp_file_deletion_approval=True),
            )

    assert await service.get_effective_settings(_ADMINISTRATOR) == saved
