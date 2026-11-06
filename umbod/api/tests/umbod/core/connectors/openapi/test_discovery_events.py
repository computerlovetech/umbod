from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import Mock

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.persistence import Database, DatabaseSession, TransactionMode
from tests.umbod.core.connectors.openapi.test_openapi_persistence_and_execution import _records
from umbod.core.connectors.openapi.management import ReplaceCurrentOpenApiCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from umbod.core.messaging.stores.event_stream import DatabaseEventStream


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def store(database: Database) -> OpenApiConnectorStore:
    return await ConfiguredOpenApiConnectorStoreFactory(database).create()


@pytest.fixture
def event_rejecting_database(database: Database) -> Database:
    @asynccontextmanager
    async def rejecting_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with database.session(mode=mode) as session:
            rejecting = Mock(spec=DatabaseSession, wraps=session)
            rejecting.insert_generated_integer_key.side_effect = RuntimeError("event append failed")
            yield rejecting

    rejecting_database = Mock(spec=Database, wraps=database)
    rejecting_database.session.side_effect = rejecting_session
    return rejecting_database


@pytest.mark.asyncio
async def test_definition_catalog_and_unpublished_deletion_emit_discovery_events(database: Database, store: OpenApiConnectorStore) -> None:
    connector, catalog = _records()
    await store.save_connector(connector)
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    await store.delete_connector(connector.connector_id)
    events = await DatabaseEventStream(database).list_after(0, 100)
    assert [entry.event.event_type for entry in events] == ["connector.discovery.changed"] * 3
    assert all(entry.event.metadata == {"connector_kind": "openapi", "connector_id": connector.connector_id} for entry in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("save", "replace_catalog", "delete"))
async def test_event_append_failure_rolls_back_openapi_mutation(
    database: Database, store: OpenApiConnectorStore, event_rejecting_database: Database, mutation: str,
) -> None:
    connector, catalog = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    rejecting_store = await ConfiguredOpenApiConnectorStoreFactory(event_rejecting_database).create()
    changed = connector.model_copy(update={"display_name": "Changed"})
    with pytest.raises(RuntimeError, match="event append failed"):
        if mutation == "save":
            await rejecting_store.save_connector(changed)
        elif mutation == "replace_catalog":
            await rejecting_store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(
                connector=changed, catalog=catalog.model_copy(update={"catalog_id": "replacement"}),
            ))
        else:
            await rejecting_store.delete_connector(connector.connector_id)
    assert await store.get_connector(connector.connector_id) == connector
    assert await store.read_current_catalog(connector.connector_id) == catalog
    assert len(await DatabaseEventStream(database).list_after(0, 100)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("configure", "clear", "publish", "unpublish"))
async def test_shared_configuration_and_publication_event_failure_rolls_back_state(
    database: Database, event_rejecting_database: Database, mutation: str,
) -> None:
    from umbod.core.configuration.models import EncryptedConnectorConfiguration
    from umbod.core.configuration.ports import EncryptedConnectorConfigurationStoreProtocol
    from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_TABLE
    from umbod.core.configuration.persistence.stores.service import EncryptedConnectorConfigurationStoreService
    from umbod.core.publishing import ConnectorPublishingStore
    from umbod.core.publishing.factories import create_connector_publishing_store

    configurations: EncryptedConnectorConfigurationStoreProtocol = EncryptedConnectorConfigurationStoreService(database, CONNECTOR_CONFIGURATION_TABLE)
    publishing: ConnectorPublishingStore = await create_connector_publishing_store(database)
    original = EncryptedConnectorConfiguration(connector_id="c", ciphertext="original")
    await configurations.save_encrypted_configuration(original)
    if mutation == "unpublish":
        await publishing.publish_connector("c")
    events_before = await DatabaseEventStream(database).list_after(0, 100)
    rejecting_configurations = EncryptedConnectorConfigurationStoreService(event_rejecting_database, CONNECTOR_CONFIGURATION_TABLE)
    rejecting_publishing = await create_connector_publishing_store(event_rejecting_database)
    with pytest.raises(RuntimeError, match="event append failed"):
        if mutation == "configure":
            await rejecting_configurations.save_encrypted_configuration(original.model_copy(update={"ciphertext": "replacement"}))
        elif mutation == "clear":
            await rejecting_configurations.delete_encrypted_configuration("c")
        elif mutation == "publish":
            await rejecting_publishing.publish_connector("c")
        else:
            await rejecting_publishing.unpublish_connector("c")
    assert await configurations.get_encrypted_configuration("c") == original
    assert await publishing.is_published("c") == (mutation == "unpublish")
    assert await DatabaseEventStream(database).list_after(0, 100) == events_before
