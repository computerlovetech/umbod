from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_TABLE
from tests.persistence_runtime import prepared_inmemory_runtime
from collections.abc import AsyncIterator
import pytest
import pytest_asyncio
from umbod.core.configuration import EncryptedConnectorConfiguration, EncryptedConnectorConfigurationStoreProtocol
from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_CONNECTOR_ID, CONNECTOR_CONFIGURATIONS, ENCRYPTED_CONNECTOR_CONFIGURATION_PROJECTION, ConnectorConfigurationKey, ConnectorConfigurationRecord
from umbod.core.persistence import Database, TransactionMode, Equals, Query, Unordered, UpsertCommand


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def store(database: Database) -> EncryptedConnectorConfigurationStoreProtocol:
    return await create_encrypted_connector_configuration_store(database)

@pytest.mark.asyncio
async def test_save_and_get_encrypted_configuration(store: EncryptedConnectorConfigurationStoreProtocol) -> None:
    configuration = EncryptedConnectorConfiguration(connector_id='slack', ciphertext='encrypted-slack-configuration')
    await store.save_encrypted_configuration(configuration)
    assert await store.get_encrypted_configuration('slack') == configuration
    assert await store.count_configurations_for_connector('slack') == 1

@pytest.mark.asyncio
async def test_save_upserts_existing_encrypted_configuration(store: EncryptedConnectorConfigurationStoreProtocol) -> None:
    await store.save_encrypted_configuration(EncryptedConnectorConfiguration(connector_id='slack', ciphertext='first'))
    await store.save_encrypted_configuration(EncryptedConnectorConfiguration(connector_id='slack', ciphertext='second'))
    assert await store.get_encrypted_configuration('slack') == EncryptedConnectorConfiguration(connector_id='slack', ciphertext='second')
    assert await store.count_configurations_for_connector('slack') == 1

@pytest.mark.asyncio
async def test_delete_encrypted_configuration_is_idempotent(store: EncryptedConnectorConfigurationStoreProtocol) -> None:
    await store.save_encrypted_configuration(EncryptedConnectorConfiguration(connector_id='slack', ciphertext='encrypted'))
    await store.delete_encrypted_configuration('slack')
    await store.delete_encrypted_configuration('slack')
    assert await store.get_encrypted_configuration('slack') is None
    assert await store.count_configurations_for_connector('slack') == 0

@pytest.mark.asyncio
async def test_encrypted_configuration_projection_excludes_updated_at(database: Database) -> None:
    await database.ensure_schema((CONNECTOR_CONFIGURATIONS,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.upsert(CONNECTOR_CONFIGURATION_TABLE, UpsertCommand(key=ConnectorConfigurationKey(connector_id='slack'), row=ConnectorConfigurationRecord(connector_id='slack', ciphertext='encrypted', updated_at='2026-01-01T00:00:00+00:00')))
        result = await session.find_one(CONNECTOR_CONFIGURATION_TABLE, Query(filter=Equals(CONNECTOR_CONFIGURATION_CONNECTOR_ID, 'slack'), projection=ENCRYPTED_CONNECTOR_CONFIGURATION_PROJECTION, ordering=Unordered()))
    assert result is not None
    assert result.model_dump() == {'connector_id': 'slack', 'ciphertext': 'encrypted'}

@pytest.mark.asyncio
async def test_store_instances_share_stored_configurations(database: Database) -> None:
    writer = await create_encrypted_connector_configuration_store(database)
    reader = await create_encrypted_connector_configuration_store(database)
    configuration = EncryptedConnectorConfiguration(connector_id='slack', ciphertext='encrypted')
    await writer.save_encrypted_configuration(configuration)
    assert await reader.get_encrypted_configuration('slack') == configuration
    assert await reader.count_configurations_for_connector('slack') == 1
