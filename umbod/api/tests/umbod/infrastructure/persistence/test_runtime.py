from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.permissions.factories import create_group_permission_store
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from umbod.infrastructure.persistence.inmemory.database import InMemoryDatabase
from umbod.infrastructure.persistence.runtime import SQLitePersistenceReadiness
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.schema_preparation import SQLiteCurrentSchemaPreparation
import asyncio
from pathlib import Path
import pytest
from umbod.config import AppConfig
from messaging.models import MessagingEvent
from umbod.core.messaging import (
    DatabaseEventCheckpointStore,
    DatabaseEventStream,
)

def test_inmemory_provider_creates_fresh_runtime_state_with_stable_database() -> None:
    config = AppConfig(connector_store={'type': 'inmemory'}).connector_store
    provider = ConfiguredPersistenceRuntimeProvider(config)
    first = provider.create()
    second = provider.create()
    assert isinstance(first.database, InMemoryDatabase)
    assert first.database is first.database
    assert first.database is not second.database

@pytest.mark.asyncio
async def test_persistence_runtime_shutdown_is_idempotent() -> None:
    runtime = ConfiguredPersistenceRuntimeProvider(AppConfig(connector_store={'type': 'inmemory'}).connector_store).create()
    await runtime.shutdown()
    await runtime.shutdown()

def test_sqlite_provider_retains_database_and_preserves_path(tmp_path: Path) -> None:
    database_path = tmp_path / 'parent' / 'runtime.sqlite3'
    config = AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(database_path)}).connector_store
    runtime = ConfiguredPersistenceRuntimeProvider(config).create()
    assert isinstance(runtime.database, SQLiteDatabase)
    assert runtime.database is runtime.database

@pytest.mark.asyncio
async def test_inmemory_runtime_readiness_prepares_application_schema() -> None:
    runtime = ConfiguredPersistenceRuntimeProvider(AppConfig(connector_store={'type': 'inmemory'}).connector_store).create()
    await runtime.readiness.ensure_ready()
    stream = DatabaseEventStream(runtime.database)
    event = await stream.append(MessagingEvent(event_type='connector.publication.changed', subject='connector:test'))
    assert event.sequence == 1
    assert await stream.list_after(0, 10) == [event]

@pytest.mark.asyncio
async def test_sqlite_runtime_readiness_owns_configuration_and_permissions(tmp_path: Path) -> None:
    from umbod.core.configuration import EncryptedConnectorConfiguration
    from umbod.core.permissions import SaveGroupPermissionsRequest
    runtime = ConfiguredPersistenceRuntimeProvider(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(tmp_path / 'runtime.sqlite3')}).connector_store).create()
    await runtime.readiness.ensure_ready()
    configuration_store = await create_encrypted_connector_configuration_store(runtime.database)
    permission_store = await create_group_permission_store(runtime.database)
    await configuration_store.save_encrypted_configuration(EncryptedConnectorConfiguration(connector_id='slack', ciphertext='encrypted'))
    await permission_store.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(), capabilities=()))
    assert await configuration_store.get_encrypted_configuration('slack') is not None
    summaries = await permission_store.list_group_identifiers()
    assert any((summary.group_id == 'engineering' for summary in summaries))

@pytest.mark.asyncio
async def test_sqlite_runtime_readiness_owns_messaging_schema_and_state(tmp_path: Path) -> None:
    config = AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(tmp_path / 'runtime.sqlite3')}).connector_store
    runtime = ConfiguredPersistenceRuntimeProvider(config).create()
    await runtime.readiness.ensure_ready()
    stream = DatabaseEventStream(runtime.database)
    checkpoints = DatabaseEventCheckpointStore(runtime.database)
    event = await stream.append(MessagingEvent(event_type='connector.publication.changed', subject='connector:test'))
    await checkpoints.save_last_processed_sequence('consumer', event.sequence)
    assert await stream.list_after(0, 10) == [event]
    assert await checkpoints.get_last_processed_sequence('consumer') == event.sequence

@pytest.mark.asyncio
async def test_sqlite_readiness_is_concurrent_and_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = 0
    received_databases: list[SQLiteDatabase] = []

    async def execute(plan: SQLiteCurrentSchemaPreparation) -> None:
        nonlocal calls
        calls += 1
        received_databases.append(plan._database)
        await asyncio.sleep(0)
    monkeypatch.setattr(SQLiteCurrentSchemaPreparation, 'execute', execute)
    database_path = str(tmp_path / 'runtime.sqlite3')
    database = SQLiteDatabase(database_path, create_parent_dirs=True)
    readiness = SQLitePersistenceReadiness(database)
    await asyncio.gather(*(readiness.ensure_ready() for _ in range(4)))
    await readiness.ensure_ready()
    assert calls == 1
    assert received_databases == [database]

@pytest.mark.asyncio
async def test_sqlite_readiness_propagates_error_and_can_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = 0

    async def execute(_plan: SQLiteCurrentSchemaPreparation) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('not ready')
    monkeypatch.setattr(SQLiteCurrentSchemaPreparation, 'execute', execute)
    database_path = str(tmp_path / 'runtime.sqlite3')
    readiness = SQLitePersistenceReadiness(SQLiteDatabase(database_path, create_parent_dirs=True))
    with pytest.raises(RuntimeError, match='not ready'):
        await readiness.ensure_ready()
    await readiness.ensure_ready()
    assert calls == 2
