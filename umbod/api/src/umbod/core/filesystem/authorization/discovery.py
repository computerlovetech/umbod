from collections.abc import Iterable
from enum import StrEnum
from typing import Self, Union

from pydantic import BaseModel, ConfigDict, model_validator

from ..models import AccessGrant, NodeId, NodeKind, Ownership, Permission, Principal, RootParent
from ..namespace import ROOT_ID
from .models import ResolvedIdentity


FILESYSTEM_DISCOVERY_CHANGED = "filesystem.discovery_changed"


class FilesystemOperation(StrEnum):
    HOME = "home"
    INSPECT = "inspect"
    INSPECT_ROOT = "inspect_root"
    LIST = "list"
    CREATE = "create"
    UPDATE_METADATA = "update_metadata"
    READ = "read"
    DELETE = "delete"
    SHARE = "share"


class AuthorizationNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    kind: NodeKind
    parent_id: Union[NodeId, RootParent]


class AuthorizationGrant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    principal: Principal
    permissions: frozenset[Permission]
    recursive: bool


class FilesystemAuthorizationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[AuthorizationNode, ...]
    ownerships: tuple[Ownership, ...]
    grants: tuple[AuthorizationGrant, ...]

    @model_validator(mode="after")
    def validate_unique_nodes_and_owners(self) -> Self:
        if len({node.node_id for node in self.nodes}) != len(self.nodes):
            raise ValueError("Duplicate authorization node")
        if len({owner.node_id for owner in self.ownerships}) != len(self.ownerships):
            raise ValueError("Duplicate authorization owner")
        return self


class EffectivePermissionEvaluator:
    def __init__(
        self, principals: frozenset[Principal], nodes: Iterable[AuthorizationNode],
        ownerships: Iterable[Ownership], grants: Iterable[Union[AccessGrant, AuthorizationGrant]],
    ) -> None:
        self._principals = principals
        self._nodes = {node.node_id: node for node in nodes}
        self._owners = {owner.node_id: owner.owner for owner in ownerships}
        self._direct: dict[NodeId, frozenset[Permission]] = {}
        self._recursive: dict[NodeId, frozenset[Permission]] = {}
        for grant in grants:
            if grant.principal not in principals:
                continue
            self._direct[grant.node_id] = self._direct.get(grant.node_id, frozenset()) | frozenset(grant.permissions)
            if grant.recursive is True:
                self._recursive[grant.node_id] = self._recursive.get(grant.node_id, frozenset()) | frozenset(grant.permissions)
        self._lineage_permissions: dict[NodeId, frozenset[Permission]] = {}
        self._invalid: set[NodeId] = set()

    def _resolve_lineage(self, node_id: NodeId) -> bool:
        path: list[NodeId] = []
        visited: set[NodeId] = set()
        current_id = node_id
        while current_id not in self._lineage_permissions:
            if current_id in visited or current_id in self._invalid or current_id not in self._nodes:
                self._invalid.update(visited)
                return False
            visited.add(current_id)
            current = self._nodes[current_id]
            path.append(current_id)
            if isinstance(current.parent_id, RootParent):
                if current_id != ROOT_ID or current.kind != NodeKind.DIRECTORY:
                    self._invalid.update(visited)
                    return False
                break
            parent = self._nodes.get(current.parent_id)
            if parent is None or parent.kind != NodeKind.DIRECTORY:
                self._invalid.update(visited)
                return False
            current_id = parent.node_id
        for current_id in reversed(path):
            current = self._nodes[current_id]
            inherited = (
                frozenset() if isinstance(current.parent_id, RootParent)
                else self._lineage_permissions[current.parent_id]
            )
            self._lineage_permissions[current_id] = inherited | (
                self._recursive.get(current_id, frozenset()) if current.kind == NodeKind.DIRECTORY else frozenset()
            )
        return node_id in self._lineage_permissions

    def permissions(self, node_id: NodeId) -> frozenset[Permission]:
        if not self._resolve_lineage(node_id) or node_id not in self._owners:
            return frozenset()
        if self._owners[node_id] in self._principals:
            return frozenset(Permission)
        return self._direct.get(node_id, frozenset()) | self._lineage_permissions[node_id]


def effective_permissions(
    principals: frozenset[Principal],
    node_id: NodeId,
    ownerships: tuple[Ownership, ...],
    grants: Iterable[Union[AccessGrant, AuthorizationGrant]],
    nodes: Iterable[AuthorizationNode],
) -> frozenset[Permission]:
    return EffectivePermissionEvaluator(principals, nodes, ownerships, grants).permissions(node_id)


def permitted_operations(
    snapshot: FilesystemAuthorizationSnapshot, identity: ResolvedIdentity
) -> frozenset[FilesystemOperation]:
    evaluator = EffectivePermissionEvaluator(identity.principals, snapshot.nodes, snapshot.ownerships, snapshot.grants)
    operations: set[FilesystemOperation] = {FilesystemOperation.HOME}
    for node in snapshot.nodes:
        permissions = evaluator.permissions(node.node_id)
        if Permission.DISCOVER not in permissions:
            continue
        operations.add(FilesystemOperation.INSPECT)
        if Permission.WRITE in permissions:
            operations.add(FilesystemOperation.UPDATE_METADATA)
        if node.node_id == ROOT_ID:
            operations.add(FilesystemOperation.INSPECT_ROOT)
        if Permission.SHARE in permissions:
            operations.add(FilesystemOperation.SHARE)
        if node.kind == NodeKind.DIRECTORY:
            operations.add(FilesystemOperation.LIST)
            if Permission.WRITE in permissions:
                operations.add(FilesystemOperation.CREATE)
        if node.kind == NodeKind.FILE:
            if Permission.READ in permissions:
                operations.add(FilesystemOperation.READ)
            if Permission.DELETE in permissions:
                operations.add(FilesystemOperation.DELETE)
    return frozenset(operations)
