import asyncio
from dataclasses import dataclass
from typing import Sequence

from messaging.models import MessagingEvent, MessagingEventType, StreamEvent
from messaging.ports import EventStream, EventStreamFactory


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
