from typing import Protocol, Sequence

from messaging.models import MessagingEvent, MessagingEventType, StreamEvent


class EventStream(Protocol):
    async def append(self, event: MessagingEvent) -> StreamEvent: ...

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]: ...

    async def list_after_types(
        self,
        sequence: int,
        limit: int,
        event_types: Sequence[MessagingEventType],
    ) -> list[StreamEvent]: ...


class EventCheckpointStore(Protocol):
    async def get_last_processed_sequence(self, consumer_id: str) -> int: ...

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None: ...


class EventStreamFactory(Protocol):
    def create(self) -> EventStream: ...


class EventCheckpointStoreFactory(Protocol):
    def create(self) -> EventCheckpointStore: ...


__all__ = [
    "EventCheckpointStore",
    "EventCheckpointStoreFactory",
    "EventStream",
    "EventStreamFactory",
]
