from tests.persistence_runtime import create_sqlite_runtime
from collections.abc import Callable
from pathlib import Path
import pytest
from umbod.core.messaging import (
    DatabaseEventCheckpointStore,
    DatabaseEventStream,
)
from messaging.in_memory import InMemoryEventCheckpointStore, InMemoryEventCheckpointStoreMessages, InMemoryEventStream
from messaging.ports import EventCheckpointStore, EventStream

def _in_memory_stream(_database_path: Path) -> InMemoryEventStream:
    return InMemoryEventStream('closed')

def _sqlite_stream(database_path: Path) -> EventStream:
    database = create_sqlite_runtime(database_path).database
    return DatabaseEventStream(database)

def _in_memory_checkpoint(_database_path: Path) -> InMemoryEventCheckpointStore:
    return InMemoryEventCheckpointStore(InMemoryEventCheckpointStoreMessages())

def _sqlite_checkpoint(database_path: Path) -> EventCheckpointStore:
    database = create_sqlite_runtime(database_path).database
    return DatabaseEventCheckpointStore(database)

@pytest.mark.asyncio
@pytest.mark.parametrize('factory', [_in_memory_stream, _sqlite_stream])
async def test_event_streams_reject_negative_sequence(tmp_path: Path, factory: Callable[[Path], EventStream]) -> None:
    with pytest.raises(ValueError, match='sequence cannot be negative'):
        await factory(tmp_path / 'events.sqlite3').list_after(-1, 1)

@pytest.mark.asyncio
@pytest.mark.parametrize('factory', [_in_memory_stream, _sqlite_stream])
async def test_event_streams_reject_negative_limit(tmp_path: Path, factory: Callable[[Path], EventStream]) -> None:
    with pytest.raises(ValueError, match='limit cannot be negative'):
        await factory(tmp_path / 'events.sqlite3').list_after(0, -1)

@pytest.mark.asyncio
@pytest.mark.parametrize('factory', [_in_memory_checkpoint, _sqlite_checkpoint])
async def test_checkpoint_stores_reject_negative_sequence(tmp_path: Path, factory: Callable[[Path], EventCheckpointStore]) -> None:
    with pytest.raises(ValueError, match='sequence cannot be negative'):
        await factory(tmp_path / 'events.sqlite3').save_last_processed_sequence('consumer', -1)
