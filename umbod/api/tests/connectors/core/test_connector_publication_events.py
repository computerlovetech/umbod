from tests.connector_event_adapters import (
    ConnectorEventCheckpointStoreAdapter,
    ConnectorPublicationEventStreamAdapter,
)
from typing import Any, cast

import pytest
from pydantic import ValidationError

from umbod.core.publishing.events import ConnectorPublicationChanged, ConnectorPublicationEventCheckpointStore, ConnectorPublicationEventStream
from messaging.in_memory import (
    InMemoryEventCheckpointStoreFactory,
    InMemoryEventCheckpointStoreMessages,
    InMemoryEventStreamFactory,
)


@pytest.fixture
def event_stream() -> ConnectorPublicationEventStreamAdapter:
    return ConnectorPublicationEventStreamAdapter(
        InMemoryEventStreamFactory("Connector publication event stream is closed").create()
    )


@pytest.fixture
def checkpoint_store() -> ConnectorEventCheckpointStoreAdapter:
    return ConnectorEventCheckpointStoreAdapter(
        InMemoryEventCheckpointStoreFactory(
            InMemoryEventCheckpointStoreMessages(
                closed_error_message="Connector publication event checkpoint store is closed",
                lower_sequence_error_message="Cannot save a lower connector publication checkpoint sequence",
            )
        ).create()
    )


@pytest.mark.asyncio
async def test_appended_event_is_returned_as_stream_event_with_sequence_one(
    event_stream: ConnectorPublicationEventStreamAdapter,
) -> None:
    stream: ConnectorPublicationEventStream = event_stream
    event = ConnectorPublicationChanged(connector_id="slack", state="published")

    stream_event = await stream.append_connector_publication_changed(event)

    assert stream_event.sequence == 1
    assert stream_event.event == event


@pytest.mark.asyncio
async def test_multiple_events_get_increasing_sequences_and_list_after_returns_later_events(
    event_stream: ConnectorPublicationEventStreamAdapter,
) -> None:
    stream: ConnectorPublicationEventStream = event_stream

    first_event = await stream.append_connector_publication_changed(
        ConnectorPublicationChanged(connector_id="slack", state="published")
    )
    second_event = await stream.append_connector_publication_changed(
        ConnectorPublicationChanged(connector_id="github", state="published")
    )
    third_event = await stream.append_connector_publication_changed(
        ConnectorPublicationChanged(connector_id="slack", state="unpublished")
    )

    later_events = await stream.list_connector_publication_changed_after(
        first_event.sequence, limit=10
    )

    assert [first_event.sequence, second_event.sequence, third_event.sequence] == [1, 2, 3]
    assert later_events == [second_event, third_event]


@pytest.mark.asyncio
async def test_list_after_respects_limit(
    event_stream: ConnectorPublicationEventStreamAdapter,
) -> None:
    stream: ConnectorPublicationEventStream = event_stream
    await stream.append_connector_publication_changed(
        ConnectorPublicationChanged(connector_id="slack", state="published")
    )
    second_event = await stream.append_connector_publication_changed(
        ConnectorPublicationChanged(connector_id="github", state="published")
    )
    await stream.append_connector_publication_changed(
        ConnectorPublicationChanged(connector_id="jira", state="published")
    )

    later_events = await stream.list_connector_publication_changed_after(1, limit=1)

    assert later_events == [second_event]


@pytest.mark.asyncio
async def test_invalid_raw_event_payload_fails_validation(
    event_stream: ConnectorPublicationEventStreamAdapter,
) -> None:
    stream: ConnectorPublicationEventStream = event_stream
    raw_event: dict[str, Any] = {"connector_id": "slack", "state": "draft"}

    with pytest.raises(ValidationError):
        await stream.append_connector_publication_changed(
            cast(ConnectorPublicationChanged, raw_event)
        )


@pytest.mark.asyncio
async def test_stream_append_and_list_after_close_raise_runtime_error(
    event_stream: ConnectorPublicationEventStreamAdapter,
) -> None:
    stream: ConnectorPublicationEventStream = event_stream

    await event_stream.close()

    with pytest.raises(RuntimeError, match="Connector publication event stream is closed"):
        await stream.append_connector_publication_changed(
            ConnectorPublicationChanged(connector_id="slack", state="published")
        )
    with pytest.raises(RuntimeError, match="Connector publication event stream is closed"):
        await stream.list_connector_publication_changed_after(0, limit=10)


@pytest.mark.asyncio
async def test_unknown_checkpoint_consumer_returns_zero(
    checkpoint_store: ConnectorEventCheckpointStoreAdapter,
) -> None:
    store: ConnectorPublicationEventCheckpointStore = checkpoint_store

    sequence = await store.get_last_processed_sequence("indexer")

    assert sequence == 0


@pytest.mark.asyncio
async def test_checkpoint_saves_and_returns_sequence(
    checkpoint_store: ConnectorEventCheckpointStoreAdapter,
) -> None:
    store: ConnectorPublicationEventCheckpointStore = checkpoint_store

    await store.save_last_processed_sequence("indexer", 3)

    assert await store.get_last_processed_sequence("indexer") == 3


@pytest.mark.asyncio
async def test_checkpoint_rejects_lower_sequence(
    checkpoint_store: ConnectorEventCheckpointStoreAdapter,
) -> None:
    store: ConnectorPublicationEventCheckpointStore = checkpoint_store

    await store.save_last_processed_sequence("indexer", 3)

    with pytest.raises(
        ValueError, match="Cannot save a lower connector publication checkpoint sequence"
    ):
        await store.save_last_processed_sequence("indexer", 2)


@pytest.mark.asyncio
async def test_checkpoint_operations_after_close_raise_runtime_error(
    checkpoint_store: ConnectorEventCheckpointStoreAdapter,
) -> None:
    store: ConnectorPublicationEventCheckpointStore = checkpoint_store

    await checkpoint_store.close()

    with pytest.raises(
        RuntimeError, match="Connector publication event checkpoint store is closed"
    ):
        await store.get_last_processed_sequence("indexer")
    with pytest.raises(
        RuntimeError, match="Connector publication event checkpoint store is closed"
    ):
        await store.save_last_processed_sequence("indexer", 1)
