from typing import Literal

from messaging.models import MessagingEvent


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


__all__ = ["connector_capability_activation_changed_event"]
