from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from messaging.in_memory import InMemoryEventCheckpointStore, InMemoryEventCheckpointStoreMessages
from messaging.ports import EventCheckpointStore, EventStream

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.messaging import InMemoryEventStream
from umbod.core.messaging import DatabaseEventCheckpointStore, DatabaseEventStream


@asynccontextmanager
async def _in_memory_stream() -> AsyncIterator[EventStream]:
    yield InMemoryEventStream("closed")


@asynccontextmanager
async def _database_stream() -> AsyncIterator[EventStream]:
    runtime = create_inmemory_runtime()
    try:
        yield DatabaseEventStream(runtime.database)
    finally:
        await runtime.shutdown()


@asynccontextmanager
async def _in_memory_checkpoint() -> AsyncIterator[EventCheckpointStore]:
    yield InMemoryEventCheckpointStore(InMemoryEventCheckpointStoreMessages())


@asynccontextmanager
async def _database_checkpoint() -> AsyncIterator[EventCheckpointStore]:
    runtime = create_inmemory_runtime()
    try:
        yield DatabaseEventCheckpointStore(runtime.database)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", [_in_memory_stream, _database_stream])
async def test_event_streams_reject_negative_sequence(
    factory: Callable[[], AbstractAsyncContextManager[EventStream]],
) -> None:
    async with factory() as stream:
        with pytest.raises(ValueError, match="sequence cannot be negative"):
            await stream.list_after(-1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", [_in_memory_stream, _database_stream])
async def test_event_streams_reject_negative_limit(
    factory: Callable[[], AbstractAsyncContextManager[EventStream]],
) -> None:
    async with factory() as stream:
        with pytest.raises(ValueError, match="limit cannot be negative"):
            await stream.list_after(0, -1)


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", [_in_memory_checkpoint, _database_checkpoint])
async def test_checkpoint_stores_reject_negative_sequence(
    factory: Callable[[], AbstractAsyncContextManager[EventCheckpointStore]],
) -> None:
    async with factory() as store:
        with pytest.raises(ValueError, match="sequence cannot be negative"):
            await store.save_last_processed_sequence("consumer", -1)
