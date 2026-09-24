import asyncio
from pathlib import Path

import pytest

from umbod.core.messaging import (
    DatabaseEventCheckpointStore,
    DatabaseEventStream,
)
from umbod.core.persistence import Database
from messaging.models import MessagingEvent
from tests.persistence_runtime import create_sqlite_runtime, prepared_sqlite_runtime


async def _database(path: Path) -> Database:
    return (await prepared_sqlite_runtime(path)).database


@pytest.mark.asyncio
async def test_sqlite_events_persist_across_stream_instances(tmp_path: Path) -> None:
    database = await _database(tmp_path / 'events.sqlite3')
    persisted = await DatabaseEventStream(database).append(
        MessagingEvent(event_type='connector.publication.changed', subject='test')
    )
    events = await DatabaseEventStream(database).list_after(0, 10)
    assert events == [persisted]


@pytest.mark.asyncio
async def test_sqlite_event_filter_is_applied_before_limit(tmp_path: Path) -> None:
    stream = DatabaseEventStream(await _database(tmp_path / 'events.sqlite3'))
    await stream.append(MessagingEvent(event_type='connector.configuration.changed', subject='first'))
    expected = await stream.append(
        MessagingEvent(event_type='connector.publication.changed', subject='second')
    )
    events = await stream.list_after_types(0, 1, ('connector.publication.changed',))
    assert events == [expected]


@pytest.mark.asyncio
async def test_sqlite_checkpoint_persists_across_store_instances(tmp_path: Path) -> None:
    database = await _database(tmp_path / 'events.sqlite3')
    await DatabaseEventCheckpointStore(database).save_last_processed_sequence('consumer', 7)
    sequence = await DatabaseEventCheckpointStore(database).get_last_processed_sequence('consumer')
    assert sequence == 7


@pytest.mark.asyncio
@pytest.mark.parametrize('sequence', [-1, -10])
async def test_sqlite_checkpoint_rejects_negative_sequence(tmp_path: Path, sequence: int) -> None:
    database = await _database(tmp_path / 'events.sqlite3')
    with pytest.raises(ValueError, match='cannot be negative'):
        await DatabaseEventCheckpointStore(database).save_last_processed_sequence('consumer', sequence)


@pytest.mark.asyncio
async def test_sqlite_checkpoint_rejects_regression_after_restart(tmp_path: Path) -> None:
    database = await _database(tmp_path / 'events.sqlite3')
    await DatabaseEventCheckpointStore(database).save_last_processed_sequence('consumer', 7)
    restarted_database = create_sqlite_runtime(tmp_path / 'events.sqlite3').database
    with pytest.raises(ValueError, match='lower checkpoint'):
        await DatabaseEventCheckpointStore(restarted_database).save_last_processed_sequence(
            'consumer', 6
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [-1, -10])
async def test_sqlite_event_stream_rejects_negative_limit(tmp_path: Path, limit: int) -> None:
    database = await _database(tmp_path / 'events.sqlite3')
    with pytest.raises(ValueError, match='limit cannot be negative'):
        await DatabaseEventStream(database).list_after(0, limit)


@pytest.mark.asyncio
async def test_sqlite_autoincrement_does_not_reuse_deleted_sequence(tmp_path: Path) -> None:
    import aiosqlite

    path = tmp_path / 'autoincrement.sqlite3'
    database = await _database(path)
    stream = DatabaseEventStream(database)
    first = await stream.append(
        MessagingEvent(event_type='connector.configuration.changed', subject='first')
    )
    async with aiosqlite.connect(path) as connection:
        await connection.execute('DELETE FROM messaging_events WHERE sequence = ?', (first.sequence,))
        await connection.commit()
    second = await stream.append(
        MessagingEvent(event_type='connector.configuration.changed', subject='second')
    )
    assert second.sequence == first.sequence + 1


@pytest.mark.asyncio
async def test_sqlite_concurrent_appends_have_unique_monotonic_sequences(tmp_path: Path) -> None:
    database = await _database(tmp_path / 'concurrent.sqlite3')
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
