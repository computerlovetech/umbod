from typing import Literal

from pydantic import ConfigDict

from umbod.proxies import Model
from umbod.core.administrator import ConnectorInventoryEntry, ObservedUserMatches
from umbod.core.administrator.connector_configuration import ConnectorConfigurableState
from umbod.core.filesystem.namespaces import SharedNamespaceView
from umbod.core.groups.models import Group
from umbod.core.permissions.domain import (
    AssignablePermissionTargets,
    GroupPermissionSet,
)


class OperationResult[Operation: str, Payload](Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Operation
    result: Payload


class AppliedGroupPermissions(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    status: Literal["applied"] = "applied"


ConnectorList = OperationResult[
    Literal["list_connectors"], tuple[ConnectorInventoryEntry, ...]
]
GroupList = OperationResult[Literal["list_groups"], tuple[Group, ...]]
PermissionTargets = OperationResult[
    Literal["list_permission_targets"], AssignablePermissionTargets
]
UserMatches = OperationResult[Literal["search_users"], ObservedUserMatches]
NamespaceList = OperationResult[Literal["list_namespaces"], list[SharedNamespaceView]]
ConnectorConfiguration = OperationResult[
    Literal["read_connector_configuration"], ConnectorConfigurableState
]
GroupPermissions = OperationResult[
    Literal["read_group_permissions"], GroupPermissionSet
]
ConnectorUpdated = OperationResult[
    Literal["update_connector_configuration"], ConnectorConfigurableState
]
PermissionsUpdated = OperationResult[
    Literal["update_group_permissions"], AppliedGroupPermissions
]
NamespaceCreated = OperationResult[Literal["create_namespace"], SharedNamespaceView]
NamespaceUpdated = OperationResult[Literal["update_namespace"], SharedNamespaceView]

DiscoverResult = (
    ConnectorList | GroupList | PermissionTargets | UserMatches | NamespaceList
)
InspectResult = ConnectorConfiguration | GroupPermissions
ApplyResult = (
    ConnectorUpdated | PermissionsUpdated | NamespaceCreated | NamespaceUpdated
)
