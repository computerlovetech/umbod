from typing import Literal

from pydantic import ConfigDict

from messaging.models import MessagingEvent
from messaging.proxies import Model


class McpGroupPermissionChanged(Model):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    action: Literal["grant", "revoke"]
    target_kind: Literal[
        "connector", "tool", "prompt", "resource", "resource_template", "capability"
    ]
    connector_id: str
    operation_name: str | None = None
    capability_kind: (
        Literal["tool", "prompt", "resource", "resource_template"] | None
    ) = None
    capability_key: str | None = None

    def to_messaging_event(self) -> MessagingEvent:
        metadata = {
            "group_id": self.group_id,
            "action": self.action,
            "target_kind": self.target_kind,
            "connector_id": self.connector_id,
        }
        if self.operation_name is not None:
            metadata["operation_name"] = self.operation_name
        if self.capability_kind is not None:
            metadata["capability_kind"] = self.capability_kind
        if self.capability_key is not None:
            metadata["capability_key"] = self.capability_key
        return MessagingEvent(
            event_type="mcp.group_permission.changed",
            subject=f"mcp-group-permission:{self.group_id}",
            metadata=metadata,
        )


__all__ = ["McpGroupPermissionChanged"]
