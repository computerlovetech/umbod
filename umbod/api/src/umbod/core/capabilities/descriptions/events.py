from typing import Literal

from pydantic import ConfigDict

from umbod.proxies import Model
from messaging.models import MessagingEvent, StreamEvent


class ConnectorCapabilityDescriptionOverrideChanged(Model):
    model_config = ConfigDict(extra="forbid")

    connector_kind: Literal["native", "downstream_mcp", "openapi"]
    connector_id: str
    action: Literal["set", "clear"]
    revision: int

    def to_messaging_event(self) -> MessagingEvent:
        return connector_capability_description_override_changed_event(
            self.connector_kind,
            self.connector_id,
            self.action,
            self.revision,
        )


class ConnectorCapabilityDescriptionOverrideChangedStreamEvent(Model):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event: ConnectorCapabilityDescriptionOverrideChanged

    @classmethod
    def from_stream_event(
        cls, stream_event: StreamEvent
    ) -> "ConnectorCapabilityDescriptionOverrideChangedStreamEvent":
        if stream_event.event.event_type != "connector.capability_description_override.changed":
            raise ValueError("Stream event is not a capability description override changed event")
        return cls(
            sequence=stream_event.sequence,
            event=ConnectorCapabilityDescriptionOverrideChanged.model_validate(
                {
                    **stream_event.event.metadata,
                    "revision": int(stream_event.event.metadata["revision"]),
                }
            ),
        )


def connector_capability_description_override_changed_event(
    connector_kind: Literal["native", "downstream_mcp", "openapi"],
    connector_id: str,
    action: Literal["set", "clear"],
    revision: int,
) -> MessagingEvent:
    event = ConnectorCapabilityDescriptionOverrideChanged(
        connector_kind=connector_kind,
        connector_id=connector_id,
        action=action,
        revision=revision,
    )
    return MessagingEvent(
        event_type="connector.capability_description_override.changed",
        subject=f"connector:{connector_id}:capability-description",
        metadata={
            "connector_kind": event.connector_kind,
            "connector_id": event.connector_id,
            "action": event.action,
            "revision": str(event.revision),
        },
    )


__all__ = [
    "ConnectorCapabilityDescriptionOverrideChanged",
    "ConnectorCapabilityDescriptionOverrideChangedStreamEvent",
    "connector_capability_description_override_changed_event",
]
