from typing import Literal

from pydantic import ConfigDict

from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.proxies import Model
from messaging.models import MessagingEvent, StreamEvent


class ConnectorCapabilityActivationChanged(Model):
    model_config = ConfigDict(extra="forbid")

    connector_kind: Literal["native", "openapi", "downstream_mcp"]
    connector_id: str
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str

    @property
    def operation_name(self) -> str:
        return self.capability_key

    @property
    def key(self) -> ConnectorToolRef:
        return ConnectorToolRef(self.connector_id, self.capability_key)

    def to_messaging_event(self) -> MessagingEvent:
        return connector_capability_activation_changed_event(
            self.connector_kind,
            self.connector_id,
            self.capability_kind,
            self.capability_key,
        )


class ConnectorCapabilityActivationChangedStreamEvent(Model):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event: ConnectorCapabilityActivationChanged

    @classmethod
    def from_stream_event(
        cls, stream_event: StreamEvent
    ) -> "ConnectorCapabilityActivationChangedStreamEvent":
        if stream_event.event.event_type != "connector.capability_activation.changed":
            raise ValueError("Stream event is not a connector capability activation changed event")
        return cls(
            sequence=stream_event.sequence,
            event=ConnectorCapabilityActivationChanged(
                connector_kind=stream_event.event.metadata["connector_kind"],
                connector_id=stream_event.event.metadata["connector_id"],
                capability_kind=stream_event.event.metadata["capability_kind"],
                capability_key=stream_event.event.metadata["capability_key"],
            ),
        )


ConnectorToolChanged = ConnectorCapabilityActivationChanged
ConnectorToolChangedStreamEvent = ConnectorCapabilityActivationChangedStreamEvent


def connector_capability_activation_changed_event(
    connector_kind: Literal["native", "openapi", "downstream_mcp"],
    connector_id: str,
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"],
    capability_key: str,
) -> MessagingEvent:
    return MessagingEvent(
        event_type="connector.capability_activation.changed",
        subject=f"connector:{connector_kind}:{connector_id}:{capability_kind}:{capability_key}",
        metadata={
            "connector_kind": connector_kind,
            "connector_id": connector_id,
            "capability_kind": capability_kind,
            "capability_key": capability_key,
        },
    )


def connector_tool_activation_changed_event(
    connector_id: str, operation_name: str, *, connector_kind: str = "native"
) -> MessagingEvent:
    return connector_capability_activation_changed_event(
        connector_kind,  # type: ignore[arg-type]
        connector_id,
        "tool",
        operation_name,
    )


__all__ = [
    "ConnectorCapabilityActivationChanged",
    "ConnectorCapabilityActivationChangedStreamEvent",
    "ConnectorToolChanged",
    "ConnectorToolChangedStreamEvent",
    "connector_capability_activation_changed_event",
    "connector_tool_activation_changed_event",
]
