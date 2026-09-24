from datetime import timezone
from typing import cast

import pytest
from pydantic import ValidationError

from messaging.in_memory import (
    InMemoryEventCheckpointStore,
    InMemoryEventCheckpointStoreFactory,
    InMemoryEventCheckpointStoreMessages,
    InMemoryEventStream,
    InMemoryEventStreamFactory,
)
from messaging.models import MessagingEvent
from messaging.ports import EventCheckpointStore, EventStream


@pytest.fixture
def event_stream() -> InMemoryEventStream:
    return InMemoryEventStreamFactory("Event stream is closed").create()


@pytest.fixture
def checkpoint_store() -> InMemoryEventCheckpointStore:
    return InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()


@pytest.mark.asyncio
async def test_generic_stream_appends_and_lists_events_after_sequence(
    event_stream: InMemoryEventStream,
) -> None:
    stream: EventStream = event_stream
    first_event = await stream.append(
        MessagingEvent(event_type="connector.configuration.changed", subject="slack")
    )
    second_event = await stream.append(
        MessagingEvent(
            event_type="connector.publication.changed",
            subject="github",
            metadata={"state": "published"},
        )
    )

    later_events = await stream.list_after(first_event.sequence, limit=10)

    assert first_event.sequence == 1
    assert second_event.sequence == 2
    assert later_events == [second_event]


@pytest.mark.asyncio
async def test_generic_stream_revalidates_raw_event_payload(
    event_stream: InMemoryEventStream,
) -> None:
    stream: EventStream = event_stream
    raw_event = {"event_type": "unknown", "subject": "slack"}

    with pytest.raises(ValidationError):
        await stream.append(cast(MessagingEvent, raw_event))


@pytest.mark.asyncio
async def test_generic_stream_operations_after_close_raise_runtime_error(
    event_stream: InMemoryEventStream,
) -> None:
    stream: EventStream = event_stream

    await event_stream.close()

    with pytest.raises(RuntimeError, match="Event stream is closed"):
        await stream.append(
            MessagingEvent(event_type="connector.configuration.changed", subject="slack")
        )
    with pytest.raises(RuntimeError, match="Event stream is closed"):
        await stream.list_after(0, limit=10)


@pytest.mark.asyncio
async def test_generic_checkpoint_store_saves_sequences(
    checkpoint_store: InMemoryEventCheckpointStore,
) -> None:
    store: EventCheckpointStore = checkpoint_store

    assert await store.get_last_processed_sequence("consumer") == 0

    await store.save_last_processed_sequence("consumer", 4)

    assert await store.get_last_processed_sequence("consumer") == 4


@pytest.mark.asyncio
async def test_generic_checkpoint_store_rejects_lower_sequence(
    checkpoint_store: InMemoryEventCheckpointStore,
) -> None:
    store: EventCheckpointStore = checkpoint_store

    await store.save_last_processed_sequence("consumer", 4)

    with pytest.raises(ValueError, match="Cannot save a lower checkpoint sequence"):
        await store.save_last_processed_sequence("consumer", 3)


def test_messaging_event_default_occurrence_time_is_utc() -> None:
    event = MessagingEvent(event_type="connector.configuration.changed", subject="slack")

    assert event.occurred_at.tzinfo == timezone.utc
