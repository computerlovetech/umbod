from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator
from umbod.rest.proxies import Model


class ConnectorCapabilityPermissionResponse(Model):
    connector_id: str
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str


class ConnectorToolPermissionResponse(Model):
    connector_id: str
    operation_name: str


class AssignableConnectorPermissionTargetResponse(Model):
    connector_id: str
    display_name: str


class AssignableCapabilityPermissionTargetResponse(Model):
    connector_id: str
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str
    display_name: str


class AssignableToolPermissionTargetResponse(Model):
    connector_id: str
    operation_name: str
    display_name: str


class AssignablePermissionTargetsResponse(Model):
    connectors: list[AssignableConnectorPermissionTargetResponse]
    capabilities: list[AssignableCapabilityPermissionTargetResponse]


class GroupPermissionResponse(Model):
    group_id: str
    connector_ids: list[str]
    capabilities: list[ConnectorCapabilityPermissionResponse]


class GroupPermissionSummaryResponse(Model):
    group_id: str


class GroupPermissionListResponse(Model):
    groups: list[GroupPermissionSummaryResponse]


class GroupPermissionDetailListResponse(Model):
    groups: list[GroupPermissionResponse]


class ConnectorPermissionUpdateRequest(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(min_length=1)
    permission_status: Literal["enabled", "disabled"]


class CapabilityPermissionUpdateRequest(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(min_length=1)
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str = Field(min_length=1)
    permission_status: Literal["enabled", "disabled"]


class UpdateGroupPermissionsApiRequest(Model):
    model_config = ConfigDict(extra="forbid")

    connectors: list[ConnectorPermissionUpdateRequest] = Field(default_factory=list)
    capabilities: list[CapabilityPermissionUpdateRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.connectors and not self.capabilities:
            raise ValueError("At least one permission change is required")
        connector_ids = [connector.connector_id for connector in self.connectors]
        if len(connector_ids) != len(set(connector_ids)):
            raise ValueError("Duplicate connector permission target")
        capability_ids = [
            (item.connector_id, item.capability_kind, item.capability_key)
            for item in self.capabilities
        ]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("Duplicate capability permission target")
        return self


class PermissionChangeResponse(Model):
    status: str
    group_id: str | None = None
    message: str | None = None
    clients_notified: bool = False
