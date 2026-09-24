from typing import Sequence

from messaging.models import MessagingEvent, MessagingEventType, StreamEvent


class NoOpEventStream:
    async def append(self, event: MessagingEvent) -> StreamEvent:
        return StreamEvent(sequence=0, event=event)

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        return []

    async def list_after_types(
        self,
        sequence: int,
        limit: int,
        event_types: Sequence[MessagingEventType],
    ) -> list[StreamEvent]:
        return []
