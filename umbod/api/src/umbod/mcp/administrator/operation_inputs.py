from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, WithJsonSchema

from umbod.proxies import Model
from umbod.core.administrator import PatchGroupPermissions, SearchObservedUsers
from umbod.core.administrator.connector_configuration import (
    ConnectorDesiredState,
    ConnectorReference,
)
from umbod.core.filesystem.namespaces import (
    CreateSharedNamespace,
    SaveSharedNamespace,
    SaveSharedNamespaceDescription,
)
from umbod.core.permissions.domain import (
    CapabilityPermissionUpdate,
    ConnectorPermissionUpdate,
)

__all__ = [
    "ApplyOperation",
    "CreateNamespace",
    "DiscoverOperation",
    "InspectOperation",
    "ListConnectors",
    "ListGroups",
    "ListNamespaces",
    "ListPermissionTargets",
    "ReadConnector",
    "ReadGroupPermissions",
    "SearchUsers",
    "UpdateConnector",
    "UpdateGroupPermissions",
    "UpdateNamespace",
]


class _OperationInput(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListConnectors(_OperationInput):
    operation: Literal["list_connectors"] = Field(
        description="List connectors and their kind and ID for configuration calls."
    )


class ListGroups(_OperationInput):
    operation: Literal["list_groups"] = Field(
        description="List registered groups and their exact group IDs."
    )


class ListPermissionTargets(_OperationInput):
    operation: Literal["list_permission_targets"] = Field(
        description="List connectors and capabilities that can be assigned in group permissions."
    )


class SearchUsers(SearchObservedUsers):
    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
        WithJsonSchema(
            {"type": "string", "pattern": r"^\s*\S(?:[\s\S]{0,198}\S)?\s*$"}
        ),
    ] = Field(
        description="Name or email substring, 1–200 characters after trimming surrounding whitespace."
    )

    operation: Literal["search_users"] = Field(
        description="Search observed users by case-insensitive substring of name or email. "
        "Leading and trailing whitespace in the required query is removed before validation."
    )


class ListNamespaces(_OperationInput):
    operation: Literal["list_namespaces"] = Field(
        description="List shared namespaces, including their IDs and current revisions."
    )


class ReadConnector(_OperationInput):
    operation: Literal["read_connector_configuration"] = Field(
        description="Read one connector's current configurable state."
    )
    connector: ConnectorReference = Field(
        description="Exact connector kind and ID returned by list_connectors."
    )


class ReadGroupPermissions(_OperationInput):
    operation: Literal["read_group_permissions"] = Field(
        description="Read one group's connector and capability permissions."
    )
    group_id: str = Field(
        strict=True,
        description="Exact group ID, without trimming; an empty string can identify a legacy group.",
    )


class UpdateConnector(_OperationInput):
    operation: Literal["update_connector_configuration"] = Field(
        description="Apply selected configuration operations to one connector."
    )
    connector: ConnectorReference = Field(
        description="Exact connector kind and ID returned by list_connectors."
    )
    desired_state: ConnectorDesiredState = Field(
        description="Partial configuration changes. Use capability keys and revisions from inspection. "
        "Do not repeat a target within an operation type, combine description override and restore, "
        "or submit more than one permission patch per group. Omit operations or pass an empty list "
        "to read the current configuration without changing it."
    )


class UpdateGroupPermissions(PatchGroupPermissions):
    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["connectors"],
                    "properties": {"connectors": {"minItems": 1}},
                },
                {
                    "required": ["capabilities"],
                    "properties": {"capabilities": {"minItems": 1}},
                },
            ]
        }
    )

    operation: Literal["update_group_permissions"] = Field(
        description="Patch permissions for the exact, nonblank group ID. Supply at least one "
        "connector or capability change and do not repeat targets. Unlisted targets are unchanged. "
        "Enabled adds a direct grant; disabled removes it, not a deny. An accepted patch can register a missing group."
    )
    connectors: tuple[ConnectorPermissionUpdate, ...] = Field(
        default=(), description="Connector IDs and their requested permission statuses."
    )
    capabilities: tuple[CapabilityPermissionUpdate, ...] = Field(
        default=(),
        description="Capability references and their requested permission statuses.",
    )


class CreateNamespace(_OperationInput):
    operation: Literal["create_namespace"] = Field(
        description="Create a shared namespace."
    )
    namespace: CreateSharedNamespace = Field(
        description="Supply a namespace name and the initial list of group grants, with no "
        "duplicate group IDs. Use an empty list for no group grants."
    )


class UpdateNamespace(_OperationInput):
    operation: Literal["update_namespace"] = Field(
        description="Update an existing shared namespace."
    )
    namespace_id: UUID = Field(
        description="Shared namespace UUID returned by list_namespaces, not its root node ID."
    )
    namespace: SaveSharedNamespaceDescription | SaveSharedNamespace = Field(
        description="Supply the current namespace revision as expected_revision, the desired name, "
        "and the full replacement list of group grants. Unlisted group grants are removed; "
        "an empty list removes all group grants. To leave the description unchanged, omit both "
        "description and expected_root_revision. To change it, supply both description "
        "(empty string clears it) and the current root_revision as expected_root_revision."
    )


DiscoverOperation = Annotated[
    ListConnectors | ListGroups | ListPermissionTargets | SearchUsers | ListNamespaces,
    Field(discriminator="operation"),
]
InspectOperation = Annotated[
    ReadConnector | ReadGroupPermissions,
    Field(discriminator="operation"),
]
ApplyOperation = Annotated[
    UpdateConnector | UpdateGroupPermissions | CreateNamespace | UpdateNamespace,
    Field(discriminator="operation"),
]
