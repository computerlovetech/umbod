from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from messaging.models import MessagingEvent, StreamEvent


class ConnectorPublicationChanged(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    state: Literal["published", "unpublished"]

    def to_messaging_event(self) -> MessagingEvent:
        return connector_publication_changed_event(self.connector_id, self.state)


class ConnectorPublicationStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event: ConnectorPublicationChanged

    @classmethod
    def from_stream_event(cls, stream_event: StreamEvent) -> "ConnectorPublicationStreamEvent":
        if stream_event.event.event_type != "connector.publication.changed":
            raise ValueError("Stream event is not a connector publication changed event")
        return cls(
            sequence=stream_event.sequence,
            event=ConnectorPublicationChanged(
                connector_id=stream_event.event.metadata["connector_id"],
                state=stream_event.event.metadata["state"],
            ),
        )


class ConnectorPublicationEventStream(Protocol):
    async def append_connector_publication_changed(
        self, event: ConnectorPublicationChanged
    ) -> ConnectorPublicationStreamEvent: ...

    async def list_connector_publication_changed_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorPublicationStreamEvent]: ...


class ConnectorPublicationEventCheckpointStore(Protocol):
    async def get_last_processed_sequence(self, consumer_id: str) -> int: ...

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None: ...


def connector_publication_changed_event(
    connector_id: str, state: Literal["published", "unpublished"]
) -> MessagingEvent:
    return MessagingEvent(
        event_type="connector.publication.changed",
        subject=f"connector:{connector_id}",
        metadata={"connector_id": connector_id, "state": state},
    )


__all__ = [
    "ConnectorPublicationChanged",
    "ConnectorPublicationEventCheckpointStore",
    "ConnectorPublicationEventStream",
    "ConnectorPublicationStreamEvent",
    "connector_publication_changed_event",
]
