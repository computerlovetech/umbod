from contextlib import AsyncExitStack

import pytest

from messaging.models import MessagingEvent
from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import AppConfig, InMemoryConnectorStoreConfig, McpConfig
from umbod.core.messaging import DatabaseEventStream
from umbod.mcp.messaging import McpMessagingAdapterFactory
from umbod.rest.factories import ConfiguredEventStreamFactory


def test_rest_factory_selects_database_stream_for_http_transport() -> None:
    settings = AppConfig(
        mcp=McpConfig(messaging_transport='http'),
        connector_store=InMemoryConnectorStoreConfig(),
    )
    assert isinstance(
        ConfiguredEventStreamFactory(settings, create_inmemory_runtime().database).create(),
        DatabaseEventStream,
    )


@pytest.mark.asyncio
async def test_rest_factory_selects_shared_runtime_stream_for_sql_transport() -> None:
    settings = AppConfig(
        mcp=McpConfig(messaging_transport='sql'),
        connector_store=InMemoryConnectorStoreConfig(),
    )
    async with AsyncExitStack() as resources:
        runtime = create_inmemory_runtime()
        resources.push_async_callback(runtime.shutdown)
        await runtime.readiness.ensure_ready()
        stream = ConfiguredEventStreamFactory(settings, runtime.database).create()
        resources.push_async_callback(stream.close)
        appended = await stream.append(
            MessagingEvent(
                event_type='connector.publication.changed',
                subject='connector:test',
                metadata={'connector_id': 'test', 'state': 'published'},
            )
        )
        assert await stream.list_after(0, 10) == [appended]
        reader = McpMessagingAdapterFactory('sql', 'http://api', runtime.database).create_projection_reader()
        assert await reader.list_after(0, 10) == [appended]
