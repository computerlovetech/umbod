from contextlib import AsyncExitStack

import pytest

from umbod.mcp.messaging import McpMessagingAdapterFactory
from umbod.mcp.messaging.transport import DatabaseProjectionEventReader, HttpProjectionEventReader
from messaging.in_memory import InMemoryEventCheckpointStore
from tests.persistence_runtime import create_inmemory_runtime


def test_http_transport_selects_http_reader_and_memory_checkpoint() -> None:
    factory = McpMessagingAdapterFactory('http', 'http://api', create_inmemory_runtime().database)
    assert isinstance(factory.create_projection_reader(), HttpProjectionEventReader)
    assert isinstance(factory.create_checkpoint_store(), InMemoryEventCheckpointStore)


@pytest.mark.asyncio
async def test_sql_transport_selects_database_reader_and_independent_replay_checkpoint() -> None:
    async with AsyncExitStack() as resources:
        runtime = create_inmemory_runtime()
        resources.push_async_callback(runtime.shutdown)
        factory = McpMessagingAdapterFactory('sql', 'http://api', runtime.database)
        async with AsyncExitStack() as checkpoint_resources:
            checkpoint_store = factory.create_checkpoint_store()
            checkpoint_resources.push_async_callback(checkpoint_store.close)
            await checkpoint_store.save_last_processed_sequence('consumer', 12)
            assert await checkpoint_store.get_last_processed_sequence('consumer') == 12
        reloaded_store = McpMessagingAdapterFactory('sql', 'http://api', runtime.database).create_checkpoint_store()
        resources.push_async_callback(reloaded_store.close)
        assert isinstance(factory.create_projection_reader(), DatabaseProjectionEventReader)
        assert await reloaded_store.get_last_processed_sequence('consumer') == 0
