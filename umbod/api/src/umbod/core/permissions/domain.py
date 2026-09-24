from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from umbod.core.capabilities.domain import CapabilityKind


PermissionChangeStatus = Literal["applied", "rejected"]
PermissionStatus = Literal["enabled", "disabled"]


@dataclass(frozen=True)
class ConnectorCapabilityRef:
    connector_id: str
    capability_kind: CapabilityKind
    capability_key: str


@dataclass(frozen=True)
class ConnectorToolRef:
    connector_id: str
    operation_name: str

    def as_capability(self) -> ConnectorCapabilityRef:
        return ConnectorCapabilityRef(
            connector_id=self.connector_id,
            capability_kind="tool",
            capability_key=self.operation_name,
        )

    @classmethod
    def from_capability(cls, capability: ConnectorCapabilityRef) -> "ConnectorToolRef":
        if capability.capability_kind != "tool":
            raise ValueError("ConnectorToolRef requires capability_kind='tool'")
        return cls(connector_id=capability.connector_id, operation_name=capability.capability_key)


@dataclass(frozen=True)
class AssignableConnectorPermissionTarget:
    connector_id: str
    display_name: str


@dataclass(frozen=True)
class AssignableCapabilityPermissionTarget:
    connector_id: str
    capability_kind: CapabilityKind
    capability_key: str
    display_name: str


@dataclass(frozen=True)
class AssignablePermissionTargets:
    connectors: tuple[AssignableConnectorPermissionTarget, ...]
    capabilities: tuple[AssignableCapabilityPermissionTarget, ...]

    @property
    def tools(self) -> tuple[AssignableCapabilityPermissionTarget, ...]:
        return tuple(
            capability
            for capability in self.capabilities
            if capability.capability_kind == "tool"
        )


class GroupPermissionSummary(BaseModel):
    group_id: str


@dataclass(frozen=True)
class GroupPermissionSet:
    group_id: str
    connector_ids: tuple[str, ...]
    capabilities: tuple[ConnectorCapabilityRef, ...]

    @property
    def tools(self) -> tuple[ConnectorToolRef, ...]:
        return tuple(
            ConnectorToolRef.from_capability(capability)
            for capability in self.capabilities
            if capability.capability_kind == "tool"
        )


@dataclass(frozen=True)
class SaveGroupPermissionsRequest:
    group_id: str
    connector_ids: tuple[str, ...]
    capabilities: tuple[ConnectorCapabilityRef, ...]


@dataclass(frozen=True)
class ConnectorPermissionUpdate:
    connector_id: str
    permission_status: PermissionStatus


@dataclass(frozen=True)
class CapabilityPermissionUpdate:
    capability: ConnectorCapabilityRef
    permission_status: PermissionStatus


@dataclass(frozen=True)
class ToolPermissionUpdate:
    tool: ConnectorToolRef
    permission_status: PermissionStatus

    def as_capability_update(self) -> CapabilityPermissionUpdate:
        return CapabilityPermissionUpdate(
            capability=self.tool.as_capability(),
            permission_status=self.permission_status,
        )


@dataclass(frozen=True)
class UpdateGroupPermissionsRequest:
    group_id: str
    connectors: tuple[ConnectorPermissionUpdate, ...]
    capabilities: tuple[CapabilityPermissionUpdate, ...]


@dataclass(frozen=True)
class PermissionChangeResult:
    status: PermissionChangeStatus
    group_id: str
    message: str | None = None
    clients_notified: bool = False


def _capability_sort_key(capability: ConnectorCapabilityRef) -> tuple[str, str, str]:
    return (capability.connector_id, capability.capability_kind, capability.capability_key)


def _tool_sort_key(tool: ConnectorToolRef) -> tuple[str, str]:
    return (tool.connector_id, tool.operation_name)
