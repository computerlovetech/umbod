import sqlite3
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.openapi_connectors.test_openapi_persistence_and_execution import _records
from umbod.core.connectors.openapi.management import ReplaceCurrentOpenApiCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from umbod.core.messaging.stores.event_stream import DatabaseEventStream


@pytest.mark.asyncio
async def test_definition_catalog_and_unpublished_deletion_emit_discovery_events(tmp_path: Path) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "events.sqlite3")
    store: OpenApiConnectorStore = await ConfiguredOpenApiConnectorStoreFactory(runtime.database).create()
    connector, catalog = _records()
    await store.save_connector(connector)
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    await store.delete_connector(connector.connector_id)
    events = await DatabaseEventStream(runtime.database).list_after(0, 100)
    assert [entry.event.event_type for entry in events] == ["connector.discovery.changed"] * 3
    assert all(entry.event.metadata == {"connector_kind": "openapi", "connector_id": connector.connector_id} for entry in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("save", "replace_catalog", "delete"))
async def test_event_append_failure_rolls_back_openapi_mutation(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "events.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    store: OpenApiConnectorStore = await ConfiguredOpenApiConnectorStoreFactory(runtime.database).create()
    connector, catalog = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON messaging_events BEGIN SELECT RAISE(ABORT, 'event append failed'); END")
    changed = connector.model_copy(update={"display_name": "Changed"})
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        if mutation == "save":
            await store.save_connector(changed)
        elif mutation == "replace_catalog":
            await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(
                connector=changed, catalog=catalog.model_copy(update={"catalog_id": "replacement"}),
            ))
        else:
            await store.delete_connector(connector.connector_id)
    assert await store.get_connector(connector.connector_id) == connector
    assert await store.read_current_catalog(connector.connector_id) == catalog
    assert len(await DatabaseEventStream(runtime.database).list_after(0, 100)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("configure", "clear", "publish", "unpublish"))
async def test_shared_configuration_and_publication_event_failure_rolls_back_state(tmp_path: Path, mutation: str) -> None:
    from umbod.core.configuration.models import EncryptedConnectorConfiguration
    from umbod.core.configuration.ports import EncryptedConnectorConfigurationStoreProtocol
    from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_TABLE
    from umbod.core.configuration.persistence.stores.service import EncryptedConnectorConfigurationStoreService
    from umbod.core.publishing import ConnectorPublishingStore
    from umbod.core.publishing.factories import create_connector_publishing_store

    path = tmp_path / "shared-events.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    configurations: EncryptedConnectorConfigurationStoreProtocol = EncryptedConnectorConfigurationStoreService(runtime.database, CONNECTOR_CONFIGURATION_TABLE)
    publishing: ConnectorPublishingStore = await create_connector_publishing_store(runtime.database)
    original = EncryptedConnectorConfiguration(connector_id="c", ciphertext="original")
    await configurations.save_encrypted_configuration(original)
    if mutation == "unpublish":
        await publishing.publish_connector("c")
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON messaging_events BEGIN SELECT RAISE(ABORT, 'event append failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        if mutation == "configure":
            await configurations.save_encrypted_configuration(original.model_copy(update={"ciphertext": "replacement"}))
        elif mutation == "clear":
            await configurations.delete_encrypted_configuration("c")
        elif mutation == "publish":
            await publishing.publish_connector("c")
        else:
            await publishing.unpublish_connector("c")
    assert await configurations.get_encrypted_configuration("c") == original
    assert await publishing.is_published("c") == (mutation == "unpublish")
