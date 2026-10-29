from dataclasses import dataclass

from messaging.ports import (
    EventCheckpointStore,
    EventCheckpointStoreFactory,
)


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
]
