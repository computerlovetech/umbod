import asyncio
from dataclasses import dataclass
from typing import Sequence

from messaging.models import MessagingEvent, MessagingEventType, StreamEvent
from messaging.ports import (
    EventCheckpointStore,
    EventCheckpointStoreFactory,
    EventStream,
    EventStreamFactory,
)


class InMemoryEventStream:
    def __init__(self, closed_error_message: str) -> None:
        self._events: list[StreamEvent] = []
        self._closed = False
        self._lock = asyncio.Lock()
        self._closed_error_message = closed_error_message

    async def append(self, event: MessagingEvent) -> StreamEvent:
        self._raise_if_closed()
        validated_event = MessagingEvent.model_validate(event)
        async with self._lock:
            self._raise_if_closed()
            stream_event = StreamEvent(
                sequence=len(self._events) + 1,
                event=validated_event,
            )
            self._events.append(stream_event)
            return stream_event

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        return await self.list_after_types(sequence, limit, ())

    async def list_after_types(
        self,
        sequence: int,
        limit: int,
        event_types: Sequence[MessagingEventType],
    ) -> list[StreamEvent]:
        self._raise_if_closed()
        if sequence < 0:
            raise ValueError("Event sequence cannot be negative")
        if limit < 0:
            raise ValueError("Event limit cannot be negative")
        allowed_types = set(event_types)
        return [
            event
            for event in self._events
            if event.sequence > sequence
            and (not allowed_types or event.event.event_type in allowed_types)
        ][:limit]

    async def close(self) -> None:
        self._closed = True

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise RuntimeError(self._closed_error_message)


@dataclass(frozen=True)
class InMemoryEventStreamFactory(EventStreamFactory):
    closed_error_message: str

    def create(self) -> EventStream:
        return InMemoryEventStream(self.closed_error_message)


@dataclass(frozen=True)
class InMemoryEventCheckpointStoreMessages:
    closed_error_message: str = "Event checkpoint store is closed"
    lower_sequence_error_message: str = "Cannot save a lower checkpoint sequence"


class InMemoryEventCheckpointStore:
    def __init__(self, messages: InMemoryEventCheckpointStoreMessages) -> None:
        self._sequences_by_consumer_id: dict[str, int] = {}
        self._closed = False
        self._closed_error_message = messages.closed_error_message
        self._lower_sequence_error_message = messages.lower_sequence_error_message

    async def get_last_processed_sequence(self, consumer_id: str) -> int:
        self._raise_if_closed()
        return self._sequences_by_consumer_id.get(consumer_id, 0)

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None:
        self._raise_if_closed()
        if sequence < 0:
            raise ValueError("Checkpoint sequence cannot be negative")
        current_sequence = self._sequences_by_consumer_id.get(consumer_id, 0)
        if sequence < current_sequence:
            raise ValueError(self._lower_sequence_error_message)
        self._sequences_by_consumer_id[consumer_id] = sequence

    async def close(self) -> None:
        self._closed = True

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise RuntimeError(self._closed_error_message)


class InMemoryEventCheckpointStoreFactory(EventCheckpointStoreFactory):
    def __init__(self, messages: InMemoryEventCheckpointStoreMessages) -> None:
        self._messages = messages

    def create(self) -> EventCheckpointStore:
        return InMemoryEventCheckpointStore(self._messages)


__all__ = [
    "InMemoryEventCheckpointStore",
    "InMemoryEventCheckpointStoreFactory",
    "InMemoryEventCheckpointStoreMessages",
    "InMemoryEventStream",
    "InMemoryEventStreamFactory",
]
