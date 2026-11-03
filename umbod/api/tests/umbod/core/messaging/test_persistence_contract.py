from pathlib import Path
from typing import cast
import asyncio

import pytest

from umbod.core.messaging import (
    DatabaseEventCheckpointStore,
    DatabaseEventStream,
)
from messaging.models import MessagingEvent
from messaging.ports import EventCheckpointStore, EventStream
from tests.umbod.core.persistence.contract_support import (
    DATABASE_ADAPTERS,
    DatabaseAdapter,
)
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime

MessagingServices = tuple[EventStream, EventCheckpointStore]


@pytest.fixture(params=DATABASE_ADAPTERS, ids=lambda adapter: cast(DatabaseAdapter, adapter).name)
def messaging_services(request: pytest.FixtureRequest, tmp_path: Path) -> MessagingServices:
    adapter = cast(DatabaseAdapter, request.param)

    async def _prepare() -> MessagingServices:
        if adapter.name == 'inmemory':
            runtime = await prepared_inmemory_runtime()
        else:
            runtime = await prepared_sqlite_runtime(tmp_path / 'contract.sqlite')
        database = runtime.database
        return DatabaseEventStream(database), DatabaseEventCheckpointStore(database)

    return asyncio.run(_prepare())



def _event(event_type: str, subject: str) -> MessagingEvent:
    return MessagingEvent.model_validate({"event_type": event_type, "subject": subject})


@pytest.mark.asyncio
async def test_event_stream_append_and_list_persist_with_monotonic_sequences(
    messaging_services: MessagingServices,
) -> None:
    stream, _ = messaging_services
    first = await stream.append(_event("connector.configuration.changed", "first"))
    second = await stream.append(_event("connector.publication.changed", "second"))

    assert first.sequence == 1
    assert second.sequence == 2
    assert await stream.list_after(0, 10) == [first, second]
    assert await stream.list_after(1, 10) == [second]


@pytest.mark.asyncio
async def test_event_stream_filters_type_before_applying_limit(
    messaging_services: MessagingServices,
) -> None:
    stream, _ = messaging_services
    await stream.append(_event("connector.configuration.changed", "excluded"))
    expected = await stream.append(_event("connector.publication.changed", "included"))

    actual = await stream.list_after_types(0, 1, ("connector.publication.changed",))

    assert actual == [expected]


@pytest.mark.asyncio
async def test_event_stream_zero_limit_returns_no_events(
    messaging_services: MessagingServices,
) -> None:
    stream, _ = messaging_services
    await stream.append(_event("connector.configuration.changed", "event"))

    assert await stream.list_after(0, 0) == []


@pytest.mark.parametrize(("sequence", "limit"), [(-1, 1), (0, -1)])
@pytest.mark.asyncio
async def test_event_stream_rejects_negative_inputs(
    messaging_services: MessagingServices, sequence: int, limit: int
) -> None:
    stream, _ = messaging_services

    with pytest.raises(ValueError, match="cannot be negative"):
        await stream.list_after(sequence, limit)


@pytest.mark.asyncio
async def test_checkpoint_store_missing_save_and_idempotent_save(
    messaging_services: MessagingServices,
) -> None:
    _, store = messaging_services

    assert await store.get_last_processed_sequence("consumer") == 0
    await store.save_last_processed_sequence("consumer", 5)
    await store.save_last_processed_sequence("consumer", 5)
    assert await store.get_last_processed_sequence("consumer") == 5


@pytest.mark.asyncio
async def test_checkpoint_store_rejects_negative_and_regressing_sequences(
    messaging_services: MessagingServices,
) -> None:
    _, store = messaging_services

    with pytest.raises(ValueError, match="cannot be negative"):
        await store.save_last_processed_sequence("consumer", -1)
    await store.save_last_processed_sequence("consumer", 5)
    with pytest.raises(ValueError, match="lower checkpoint"):
        await store.save_last_processed_sequence("consumer", 4)


@pytest.mark.asyncio
async def test_concurrent_checkpoint_writes_preserve_maximum(
    messaging_services: MessagingServices,
) -> None:
    _, store = messaging_services

    results = await asyncio.gather(
        *(store.save_last_processed_sequence("consumer", sequence) for sequence in (2, 9, 4, 7)),
        return_exceptions=True,
    )

    assert await store.get_last_processed_sequence("consumer") == 9
    assert all(result is None or isinstance(result, ValueError) for result in results)
