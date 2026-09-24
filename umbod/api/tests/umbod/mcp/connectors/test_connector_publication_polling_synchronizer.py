from tests.connector_event_adapters import (
    ConnectorEventCheckpointStoreAdapter,
)
import pytest

from umbod.mcp.connectors import (
    CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT,
    CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS,
    ConnectorPublicationPollingSynchronizer,
)
from umbod.core.publishing.events import ConnectorPublicationChanged, ConnectorPublicationStreamEvent
from messaging.in_memory import (
    InMemoryEventCheckpointStoreFactory,
    InMemoryEventCheckpointStoreMessages,
)


class RecordingStreamReader:
    def __init__(self, events: list[ConnectorPublicationStreamEvent]) -> None:
        self.events = events
        self.calls: list[tuple[int, int]] = []

    async def list_after(self, sequence: int, limit: int) -> list[ConnectorPublicationStreamEvent]:
        self.calls.append((sequence, limit))
        return [event for event in self.events if event.sequence > sequence][:limit]


def make_checkpoint_store() -> ConnectorEventCheckpointStoreAdapter:
    return ConnectorEventCheckpointStoreAdapter(
        InMemoryEventCheckpointStoreFactory(
            InMemoryEventCheckpointStoreMessages(
                closed_error_message="Connector publication event checkpoint store is closed",
                lower_sequence_error_message="Cannot save a lower connector publication checkpoint sequence",
            )
        ).create()
    )


def stream_event(sequence: int, connector_id: str) -> ConnectorPublicationStreamEvent:
    return ConnectorPublicationStreamEvent(
        sequence=sequence,
        event=ConnectorPublicationChanged(connector_id=connector_id, state="published"),
    )


@pytest.mark.asyncio
async def test_poll_once_reads_events_after_checkpoint_and_saves_after_successful_handler() -> None:
    checkpoint_store = make_checkpoint_store()
    await checkpoint_store.save_last_processed_sequence("consumer", 1)
    reader = RecordingStreamReader([stream_event(1, "ignored"), stream_event(2, "slack")])
    handled_connector_ids: list[str] = []

    async def handle(connector_id: str) -> None:
        handled_connector_ids.append(connector_id)

    synchronizer = ConnectorPublicationPollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=reader,
        handler=handle,
        interval_seconds=CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS,
        batch_limit=CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT,
    )

    await synchronizer.poll_once()

    assert reader.calls == [(1, CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT)]
    assert handled_connector_ids == ["slack"]
    assert await checkpoint_store.get_last_processed_sequence("consumer") == 2


@pytest.mark.asyncio
async def test_poll_once_does_not_advance_checkpoint_when_handler_fails() -> None:
    checkpoint_store = make_checkpoint_store()
    reader = RecordingStreamReader([stream_event(1, "slack"), stream_event(2, "github")])
    handled_connector_ids: list[str] = []

    async def handle(connector_id: str) -> None:
        handled_connector_ids.append(connector_id)
        if connector_id == "github":
            raise RuntimeError("failed")

    synchronizer = ConnectorPublicationPollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=reader,
        handler=handle,
        interval_seconds=CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS,
        batch_limit=CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT,
    )

    with pytest.raises(RuntimeError, match="failed"):
        await synchronizer.poll_once()

    assert handled_connector_ids == ["slack", "github"]
    assert await checkpoint_store.get_last_processed_sequence("consumer") == 1


@pytest.mark.asyncio
async def test_repeated_polling_processes_later_events() -> None:
    checkpoint_store = make_checkpoint_store()
    reader = RecordingStreamReader([stream_event(1, "slack")])
    handled_connector_ids: list[str] = []

    def handle(connector_id: str) -> None:
        handled_connector_ids.append(connector_id)

    synchronizer = ConnectorPublicationPollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=reader,
        handler=handle,
        interval_seconds=CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS,
        batch_limit=CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT,
    )

    await synchronizer.poll_once()
    reader.events.append(stream_event(2, "github"))
    await synchronizer.poll_once()

    assert reader.calls == [
        (0, CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT),
        (1, CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT),
    ]
    assert handled_connector_ids == ["slack", "github"]
    assert await checkpoint_store.get_last_processed_sequence("consumer") == 2
