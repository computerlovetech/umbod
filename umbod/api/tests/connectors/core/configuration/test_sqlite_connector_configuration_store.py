from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_TABLE
from umbod.core.configuration.persistence.stores.service import EncryptedConnectorConfigurationStoreService
from tests.persistence_runtime import create_inmemory_runtime, prepared_inmemory_runtime, prepared_sqlite_runtime
from collections.abc import Awaitable, Callable
from pathlib import Path
import pytest
from umbod.core.configuration import EncryptedConnectorConfiguration, EncryptedConnectorConfigurationStoreProtocol
from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_CONNECTOR_ID, CONNECTOR_CONFIGURATIONS, ENCRYPTED_CONNECTOR_CONFIGURATION_PROJECTION, ConnectorConfigurationKey, ConnectorConfigurationRecord
from umbod.core.persistence import TransactionMode, Equals, Query, Unordered, UpsertCommand
ConfigurationStoreFactory = Callable[[Path], Awaitable[EncryptedConnectorConfigurationStoreProtocol]]

async def _in_memory_configuration_store(_tmp_path: Path) -> EncryptedConnectorConfigurationStoreProtocol:
    database = (await prepared_inmemory_runtime()).database
    return EncryptedConnectorConfigurationStoreService(database, CONNECTOR_CONFIGURATION_TABLE)

async def _sqlite_configuration_store(tmp_path: Path) -> EncryptedConnectorConfigurationStoreProtocol:
    database = (await prepared_sqlite_runtime(tmp_path / 'connectors.sqlite')).database
    return await create_encrypted_connector_configuration_store(database)

@pytest.fixture(params=[_in_memory_configuration_store, _sqlite_configuration_store])
def configuration_store_factory(request: pytest.FixtureRequest) -> ConfigurationStoreFactory:
    return request.param

@pytest.mark.asyncio
async def test_save_and_get_encrypted_configuration(configuration_store_factory: ConfigurationStoreFactory, tmp_path: Path) -> None:
    store = await configuration_store_factory(tmp_path)
    configuration = EncryptedConnectorConfiguration(connector_id='slack', ciphertext='encrypted-slack-configuration')
    await store.save_encrypted_configuration(configuration)
    assert await store.get_encrypted_configuration('slack') == configuration
    assert await store.count_configurations_for_connector('slack') == 1

@pytest.mark.asyncio
async def test_save_upserts_existing_encrypted_configuration(configuration_store_factory: ConfigurationStoreFactory, tmp_path: Path) -> None:
    store = await configuration_store_factory(tmp_path)
    await store.save_encrypted_configuration(EncryptedConnectorConfiguration(connector_id='slack', ciphertext='first'))
    await store.save_encrypted_configuration(EncryptedConnectorConfiguration(connector_id='slack', ciphertext='second'))
    assert await store.get_encrypted_configuration('slack') == EncryptedConnectorConfiguration(connector_id='slack', ciphertext='second')
    assert await store.count_configurations_for_connector('slack') == 1

@pytest.mark.asyncio
async def test_delete_encrypted_configuration_is_idempotent(configuration_store_factory: ConfigurationStoreFactory, tmp_path: Path) -> None:
    store = await configuration_store_factory(tmp_path)
    await store.save_encrypted_configuration(EncryptedConnectorConfiguration(connector_id='slack', ciphertext='encrypted'))
    await store.delete_encrypted_configuration('slack')
    await store.delete_encrypted_configuration('slack')
    assert await store.get_encrypted_configuration('slack') is None
    assert await store.count_configurations_for_connector('slack') == 0

@pytest.mark.asyncio
async def test_encrypted_configuration_projection_excludes_updated_at() -> None:
    database = create_inmemory_runtime().database
    await database.ensure_schema((CONNECTOR_CONFIGURATIONS,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.upsert(CONNECTOR_CONFIGURATION_TABLE, UpsertCommand(key=ConnectorConfigurationKey(connector_id='slack'), row=ConnectorConfigurationRecord(connector_id='slack', ciphertext='encrypted', updated_at='2026-01-01T00:00:00+00:00')))
        result = await session.find_one(CONNECTOR_CONFIGURATION_TABLE, Query(filter=Equals(CONNECTOR_CONFIGURATION_CONNECTOR_ID, 'slack'), projection=ENCRYPTED_CONNECTOR_CONFIGURATION_PROJECTION, ordering=Unordered()))
    assert result is not None
    assert result.model_dump() == {'connector_id': 'slack', 'ciphertext': 'encrypted'}

@pytest.mark.asyncio
async def test_sqlite_store_instances_share_persisted_configurations(tmp_path: Path) -> None:
    database_path = str(tmp_path / 'connectors.sqlite')
    database = (await prepared_sqlite_runtime(database_path)).database
    writer = await create_encrypted_connector_configuration_store(database)
    reader = await create_encrypted_connector_configuration_store(database)
    configuration = EncryptedConnectorConfiguration(connector_id='slack', ciphertext='encrypted')
    await writer.save_encrypted_configuration(configuration)
    assert await reader.get_encrypted_configuration('slack') == configuration
    assert await reader.count_configurations_for_connector('slack') == 1
