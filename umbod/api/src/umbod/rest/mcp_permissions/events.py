from typing import Literal

from umbod.core.permissions import ConnectorCapabilityRef, GroupPermissionSet
from messaging.events import McpGroupPermissionChanged
from messaging.ports import EventStream


class McpPermissionEventPublisher:
    def __init__(self, event_stream: EventStream) -> None:
        self._event_stream = event_stream

    async def publish_saved_permission_changes(
        self,
        previous_permissions: GroupPermissionSet,
        next_permissions: GroupPermissionSet,
    ) -> None:
        previous_connectors = set(previous_permissions.connector_ids)
        next_connectors = set(next_permissions.connector_ids)
        previous_capabilities = set(previous_permissions.capabilities)
        next_capabilities = set(next_permissions.capabilities)
        for connector_id in sorted(next_connectors - previous_connectors):
            await self.publish_connector_permission_changed(
                next_permissions.group_id, "grant", connector_id
            )
        for connector_id in sorted(previous_connectors - next_connectors):
            await self.publish_connector_permission_changed(
                next_permissions.group_id, "revoke", connector_id
            )
        for capability in sorted(
            next_capabilities - previous_capabilities,
            key=lambda item: (item.connector_id, item.capability_kind, item.capability_key),
        ):
            await self.publish_capability_permission_changed(
                next_permissions.group_id, "grant", capability
            )
        for capability in sorted(
            previous_capabilities - next_capabilities,
            key=lambda item: (item.connector_id, item.capability_kind, item.capability_key),
        ):
            await self.publish_capability_permission_changed(
                next_permissions.group_id, "revoke", capability
            )

    async def publish_connector_permission_changed(
        self,
        group_id: str,
        action: Literal["grant", "revoke"],
        connector_id: str,
    ) -> None:
        await self._event_stream.append(
            McpGroupPermissionChanged(
                group_id=group_id,
                action=action,
                target_kind="connector",
                connector_id=connector_id,
            ).to_messaging_event()
        )

    async def publish_capability_permission_changed(
        self,
        group_id: str,
        action: Literal["grant", "revoke"],
        capability: ConnectorCapabilityRef,
    ) -> None:
        await self._event_stream.append(
            McpGroupPermissionChanged(
                group_id=group_id,
                action=action,
                target_kind=capability.capability_kind,
                connector_id=capability.connector_id,
                capability_kind=capability.capability_kind,
                capability_key=capability.capability_key,
                operation_name=(
                    capability.capability_key if capability.capability_kind == "tool" else None
                ),
            ).to_messaging_event()
        )

    async def publish_tool_permission_changed(
        self,
        group_id: str,
        action: Literal["grant", "revoke"],
        tool: ConnectorCapabilityRef,
    ) -> None:
        await self.publish_capability_permission_changed(group_id, action, tool)
