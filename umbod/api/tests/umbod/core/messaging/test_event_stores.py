import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from umbod.core.messaging import (
    DatabaseEventCheckpointStore,
    DatabaseEventStream,
)
from umbod.core.persistence import Database
from messaging.models import MessagingEvent
from tests.persistence_runtime import prepared_inmemory_runtime


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_events_persist_across_stream_instances(database: Database) -> None:
    persisted = await DatabaseEventStream(database).append(
        MessagingEvent(event_type='connector.publication.changed', subject='test')
    )
    events = await DatabaseEventStream(database).list_after(0, 10)
    assert events == [persisted]


@pytest.mark.asyncio
async def test_event_filter_is_applied_before_limit(database: Database) -> None:
    stream = DatabaseEventStream(database)
    await stream.append(MessagingEvent(event_type='connector.configuration.changed', subject='first'))
    expected = await stream.append(
        MessagingEvent(event_type='connector.publication.changed', subject='second')
    )
    events = await stream.list_after_types(0, 1, ('connector.publication.changed',))
    assert events == [expected]


@pytest.mark.asyncio
async def test_checkpoint_persists_across_store_instances(database: Database) -> None:
    await DatabaseEventCheckpointStore(database).save_last_processed_sequence('consumer', 7)
    sequence = await DatabaseEventCheckpointStore(database).get_last_processed_sequence('consumer')
    assert sequence == 7


@pytest.mark.asyncio
@pytest.mark.parametrize('sequence', [-1, -10])
async def test_checkpoint_rejects_negative_sequence(database: Database, sequence: int) -> None:
    with pytest.raises(ValueError, match='cannot be negative'):
        await DatabaseEventCheckpointStore(database).save_last_processed_sequence('consumer', sequence)


@pytest.mark.asyncio
async def test_checkpoint_rejects_regression_across_store_instances(database: Database) -> None:
    await DatabaseEventCheckpointStore(database).save_last_processed_sequence('consumer', 7)
    with pytest.raises(ValueError, match='lower checkpoint'):
        await DatabaseEventCheckpointStore(database).save_last_processed_sequence(
            'consumer', 6
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [-1, -10])
async def test_event_stream_rejects_negative_limit(database: Database, limit: int) -> None:
    with pytest.raises(ValueError, match='limit cannot be negative'):
        await DatabaseEventStream(database).list_after(0, limit)


@pytest.mark.asyncio
async def test_concurrent_appends_have_unique_monotonic_sequences(database: Database) -> None:
    streams = [DatabaseEventStream(database) for _ in range(12)]
    appended = await asyncio.gather(
        *(
            stream.append(
                MessagingEvent(event_type='connector.configuration.changed', subject=str(index))
            )
            for (index, stream) in enumerate(streams)
        )
    )
    sequences = sorted((event.sequence for event in appended))
    assert sequences == list(range(1, len(streams) + 1))
