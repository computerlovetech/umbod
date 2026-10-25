from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Protocol

from umbod.core.callers import GroupMembership
from umbod.core.capabilities.domain import CapabilityKind


@dataclass(frozen=True)
class ConnectorCapabilityPermission:
    connector_id: str
    capability_kind: CapabilityKind
    capability_key: str


@dataclass(frozen=True)
class ConnectorToolPermission:
    connector_id: str
    operation_name: str

    def as_capability(self) -> ConnectorCapabilityPermission:
        return ConnectorCapabilityPermission(
            connector_id=self.connector_id,
            capability_kind="tool",
            capability_key=self.operation_name,
        )


@dataclass
class GroupConnectorToolPermissionState:
    group_claim_fields: tuple[str, ...]
    connector_grants_by_group: dict[str, set[str]]
    capability_grants_by_group: dict[str, set[ConnectorCapabilityPermission]]

    @property
    def tool_grants_by_group(self) -> dict[str, set[ConnectorToolPermission]]:
        return {
            group: {
                ConnectorToolPermission(
                    connector_id=permission.connector_id,
                    operation_name=permission.capability_key,
                )
                for permission in permissions
                if permission.capability_kind == "tool"
            }
            for group, permissions in self.capability_grants_by_group.items()
        }


class RuntimeGroupPermissions(Protocol):
    allowed_connector_ids: Callable[[GroupMembership], set[str]]
    allowed_tools: Callable[[GroupMembership], set[ConnectorToolPermission]]
    allowed_capabilities: Callable[[GroupMembership], set[ConnectorCapabilityPermission]]


class InMemoryGroupConnectorToolPermissions:
    grant_connector: Callable[[str, str], None]
    grant_tool: Callable[[str, str, str], None]
    grant_capability: Callable[[str, str, CapabilityKind, str], None]
    allowed_connector_ids: Callable[[GroupMembership], set[str]]
    allowed_tools: Callable[[GroupMembership], set[ConnectorToolPermission]]
    allowed_capabilities: Callable[[GroupMembership], set[ConnectorCapabilityPermission]]
    replace_group_permissions: Callable[
        [Mapping[str, Iterable[str]], Mapping[str, Iterable[ConnectorCapabilityPermission]]],
        None,
    ]
    validate_connector_tool_change: Callable[..., None]

    def __init__(self, *, group_claim_fields: Sequence[str]) -> None:
        state = GroupConnectorToolPermissionState(
            group_claim_fields=tuple(group_claim_fields),
            connector_grants_by_group={},
            capability_grants_by_group={},
        )
        self.group_claim_fields = state.group_claim_fields
        self._state = state
        self.grant_connector = partial(_grant_connector, state)
        self.grant_tool = partial(_grant_tool, state)
        self.grant_capability = partial(_grant_capability, state)
        self.allowed_connector_ids = partial(_allowed_connector_ids, state)
        self.allowed_tools = partial(_allowed_tools, state)
        self.allowed_capabilities = partial(_allowed_capabilities, state)
        self.replace_group_permissions = partial(_replace_group_permissions, state)
        self.validate_connector_tool_change = partial(_validate_connector_tool_change, state)


def _grant_connector(
    state: GroupConnectorToolPermissionState, group: str, connector_id: str
) -> None:
    state.connector_grants_by_group.setdefault(group, set()).add(connector_id)


def _grant_tool(
    state: GroupConnectorToolPermissionState, group: str, connector_id: str, operation_name: str
) -> None:
    _grant_capability(state, group, connector_id, "tool", operation_name)


def _grant_capability(
    state: GroupConnectorToolPermissionState,
    group: str,
    connector_id: str,
    capability_kind: CapabilityKind,
    capability_key: str,
) -> None:
    state.capability_grants_by_group.setdefault(group, set()).add(
        ConnectorCapabilityPermission(
            connector_id=connector_id,
            capability_kind=capability_kind,
            capability_key=capability_key,
        )
    )


def _replace_group_permissions(
    state: GroupConnectorToolPermissionState,
    connector_grants_by_group: Mapping[str, Iterable[str]],
    capability_grants_by_group: Mapping[
        str, Iterable[ConnectorCapabilityPermission | ConnectorToolPermission]
    ],
) -> None:
    state.connector_grants_by_group.clear()
    state.connector_grants_by_group.update(
        {group: set(connector_ids) for group, connector_ids in connector_grants_by_group.items()}
    )
    state.capability_grants_by_group.clear()
    normalized: dict[str, set[ConnectorCapabilityPermission]] = {}
    for group, permissions in capability_grants_by_group.items():
        normalized[group] = {
            permission.as_capability()
            if isinstance(permission, ConnectorToolPermission)
            else permission
            for permission in permissions
        }
    state.capability_grants_by_group.update(normalized)


def _allowed_connector_ids(
    state: GroupConnectorToolPermissionState, membership: GroupMembership
) -> set[str]:
    connector_ids: set[str] = set()
    for group in membership.group_ids:
        connector_ids.update(state.connector_grants_by_group.get(group, set()))
        connector_ids.update(
            permission.connector_id
            for permission in state.capability_grants_by_group.get(group, set())
        )
    return connector_ids


def _allowed_tools(
    state: GroupConnectorToolPermissionState,
    membership: GroupMembership,
) -> set[ConnectorToolPermission]:
    return {
        ConnectorToolPermission(
            connector_id=permission.connector_id,
            operation_name=permission.capability_key,
        )
        for permission in _allowed_capabilities(state, membership)
        if permission.capability_kind == "tool"
    }


def _allowed_capabilities(
    state: GroupConnectorToolPermissionState,
    membership: GroupMembership,
) -> set[ConnectorCapabilityPermission]:
    permissions: set[ConnectorCapabilityPermission] = set()
    for group in membership.group_ids:
        permissions.update(state.capability_grants_by_group.get(group, set()))
    return permissions


def _validate_connector_tool_change(
    state: GroupConnectorToolPermissionState,
    *,
    connector_id: str,
    previous_tool_names: set[str],
    next_tool_names: set[str],
) -> None:
    removed_tool_names = previous_tool_names - next_tool_names
    granted_removed_tool_names = {
        permission.capability_key
        for permissions in state.capability_grants_by_group.values()
        for permission in permissions
        if permission.connector_id == connector_id
        and permission.capability_kind == "tool"
        and permission.capability_key in removed_tool_names
    }
    if granted_removed_tool_names:
        raise ValueError("Connector tool change would break an existing permission mapping")
