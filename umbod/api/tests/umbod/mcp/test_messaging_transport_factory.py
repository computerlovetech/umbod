from pathlib import Path

import pytest

from umbod.config import AppConfig, ConnectorStoreConfig, McpConfig
from umbod.mcp.connectors import HttpConnectorPublicationStreamReader
from umbod.mcp.messaging import DatabaseDomainEventReader, McpMessagingAdapterFactory
from umbod.rest.factories import ConfiguredEventStreamFactory
from messaging.in_memory import InMemoryEventCheckpointStore, InMemoryEventStream
from messaging.models import MessagingEvent
from tests.persistence_runtime import create_inmemory_runtime, create_sqlite_runtime, prepared_sqlite_runtime


def test_http_transport_selects_http_reader_and_memory_checkpoint() -> None:
    factory = McpMessagingAdapterFactory('http', 'http://api', create_inmemory_runtime().database)
    assert isinstance(factory.create_publication_reader(), HttpConnectorPublicationStreamReader)
    assert isinstance(factory.create_checkpoint_store(), InMemoryEventCheckpointStore)


@pytest.mark.asyncio
async def test_sql_transport_selects_sql_reader_and_durable_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / 'events.sqlite3'
    database = (await prepared_sqlite_runtime(path)).database
    factory = McpMessagingAdapterFactory('sql', 'http://api', database)
    checkpoint_store = factory.create_checkpoint_store()
    await checkpoint_store.save_last_processed_sequence('consumer', 12)
    await checkpoint_store.close()
    restarted_database = create_sqlite_runtime(path).database
    reloaded_store = McpMessagingAdapterFactory('sql', 'http://api', restarted_database).create_checkpoint_store()
    assert isinstance(factory.create_publication_reader(), DatabaseDomainEventReader)
    assert await reloaded_store.get_last_processed_sequence('consumer') == 12
    await reloaded_store.close()


def test_rest_factory_selects_memory_stream_for_http_transport(tmp_path: Path) -> None:
    settings = AppConfig(
        mcp=McpConfig(messaging_transport='http'),
        connector_store=ConnectorStoreConfig(sqlite_path=str(tmp_path / 'events.sqlite3')),
    )
    assert isinstance(
        ConfiguredEventStreamFactory(settings, create_inmemory_runtime().database).create(),
        InMemoryEventStream,
    )


@pytest.mark.asyncio
async def test_rest_factory_selects_shared_runtime_stream_for_sql_transport(tmp_path: Path) -> None:
    settings = AppConfig(
        mcp=McpConfig(messaging_transport='sql'),
        connector_store=ConnectorStoreConfig(sqlite_path=str(tmp_path / 'events.sqlite3')),
    )
    database = (await prepared_sqlite_runtime(tmp_path / 'events.sqlite3')).database
    stream = ConfiguredEventStreamFactory(settings, database).create()
    appended = await stream.append(
        MessagingEvent(
            event_type='connector.publication.changed',
            subject='connector:test',
            metadata={'connector_id': 'test', 'state': 'published'},
        )
    )
    assert await stream.list_after(0, 10) == [appended]
    await stream.close()
