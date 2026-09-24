from typing import Protocol

from pydantic import ConfigDict

from umbod.proxies import Model
from messaging.models import MessagingEvent, StreamEvent


class ConnectorRuntimeStateChanged(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str

    def to_messaging_event(self) -> MessagingEvent:
        return connector_configuration_changed_event(self.connector_id)


class ConnectorRuntimeStateStreamEvent(Model):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event: ConnectorRuntimeStateChanged

    @classmethod
    def from_stream_event(cls, stream_event: StreamEvent) -> "ConnectorRuntimeStateStreamEvent":
        if stream_event.event.event_type != "connector.configuration.changed":
            raise ValueError("Stream event is not a connector runtime state changed event")
        return cls(
            sequence=stream_event.sequence,
            event=ConnectorRuntimeStateChanged(
                connector_id=stream_event.event.metadata["connector_id"]
            ),
        )


class ConnectorRuntimeStateEventStream(Protocol):
    async def append_connector_runtime_state_changed(
        self, event: ConnectorRuntimeStateChanged
    ) -> ConnectorRuntimeStateStreamEvent: ...

    async def list_connector_runtime_state_changed_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorRuntimeStateStreamEvent]: ...


def connector_configuration_changed_event(connector_id: str) -> MessagingEvent:
    return MessagingEvent(
        event_type="connector.configuration.changed",
        subject=f"connector:{connector_id}",
        metadata={"connector_id": connector_id},
    )


__all__ = [
    "ConnectorRuntimeStateChanged",
    "ConnectorRuntimeStateEventStream",
    "ConnectorRuntimeStateStreamEvent",
    "connector_configuration_changed_event",
]
