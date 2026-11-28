from collections.abc import Iterable
from enum import StrEnum
from typing import Self, Union

from pydantic import ConfigDict, model_validator

from umbod.proxies import Model

from ..models import AccessGrant, NodeId, NodeKind, Ownership, Permission, Principal, RootParent
from ..namespace import ROOT_ID
from ..namespaces.models import NamespacePolicy
from .models import ResolvedIdentity


FILESYSTEM_DISCOVERY_CHANGED = "filesystem.discovery_changed"


class FilesystemOperation(StrEnum):
    HOME = "home"
    INSPECT = "inspect"
    LIST = "list"
    CREATE = "create"
    UPDATE_METADATA = "update_metadata"
    READ = "read"
    DELETE = "delete"
    SHARE = "share"


class AuthorizationNode(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    kind: NodeKind
    parent_id: Union[NodeId, RootParent]


class AuthorizationGrant(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    principal: Principal
    permissions: frozenset[Permission]
    recursive: bool


class FilesystemAuthorizationSnapshot(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[AuthorizationNode, ...]
    ownerships: tuple[Ownership, ...]
    grants: tuple[AuthorizationGrant, ...]
    namespaces: tuple[NamespacePolicy, ...]

    @model_validator(mode="after")
    def validate_unique_nodes(self) -> Self:
        if len({node.node_id for node in self.nodes}) != len(self.nodes):
            raise ValueError("Duplicate authorization node")
        if len({owner.node_id for owner in self.ownerships}) != len(self.ownerships):
            raise ValueError("Duplicate authorization owner")
        return self


class EffectivePermissionEvaluator:
    def __init__(
        self, principals: frozenset[Principal], nodes: Iterable[AuthorizationNode],
        ownerships: Iterable[Ownership], grants: Iterable[AccessGrant | AuthorizationGrant],
        namespaces: Iterable[NamespacePolicy],
    ) -> None:
        self._principals = principals
        policies = tuple(namespaces)
        self._namespaces = {policy.root_node_id: policy for policy in policies}
        if len(self._namespaces) != len(policies):
            raise ValueError("Duplicate namespace roots")
        ancestry = tuple(nodes)
        self._nodes = {node.node_id: node for node in ancestry}
        if len(self._nodes) != len(ancestry):
            raise ValueError("Duplicate authorization node")
        self._owners = {owner.node_id: owner.owner for owner in ownerships}
        self._direct: dict[NodeId, frozenset[Permission]] = {}
        self._recursive: dict[NodeId, frozenset[Permission]] = {}
        for grant in grants:
            if grant.principal not in principals:
                continue
            permissions = frozenset(grant.permissions)
            self._direct[grant.node_id] = self._direct.get(grant.node_id, frozenset()) | permissions
            if grant.recursive is True:
                self._recursive[grant.node_id] = self._recursive.get(grant.node_id, frozenset()) | permissions
        self._inherited: dict[NodeId, frozenset[Permission]] = {}
        self._valid: set[NodeId] = set()
        self._invalid: set[NodeId] = set()

    def _resolve_lineage(self, node_id: NodeId) -> bool:
        visited: set[NodeId] = set()
        current_id = node_id
        while current_id not in self._valid:
            if current_id in visited or current_id in self._invalid or current_id not in self._nodes:
                self._invalid.update(visited)
                return False
            visited.add(current_id)
            current = self._nodes[current_id]
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
        self._valid.update(visited)
        return True

    def namespace(self, node_id: NodeId) -> NamespacePolicy | None:
        if node_id == ROOT_ID or not self._resolve_lineage(node_id):
            return None
        while node_id != ROOT_ID:
            if node_id in self._namespaces:
                policy = self._namespaces[node_id]
                return policy if self._nodes[node_id].kind == NodeKind.DIRECTORY else None
            parent = self._nodes[node_id].parent_id
            if isinstance(parent, RootParent):
                return None
            node_id = parent
        return None

    def permissions(self, node_id: NodeId) -> frozenset[Permission]:
        policy = self.namespace(node_id)
        if policy is None:
            return frozenset()
        baseline = policy.permissions(self._principals)
        if node_id == policy.root_node_id:
            return baseline
        if self._owners.get(node_id) in self._principals:
            return frozenset(Permission)
        if policy.kind == "personal" and policy.owners.intersection(self._principals):
            baseline |= {Permission.SHARE}
        return baseline | self._direct.get(node_id, frozenset()) | self._ancestor_permissions(node_id, policy.root_node_id)

    def _ancestor_permissions(self, node_id: NodeId, namespace_root: NodeId) -> frozenset[Permission]:
        path: list[NodeId] = []
        current_id = node_id
        while current_id != namespace_root and current_id not in self._inherited:
            path.append(current_id)
            parent = self._nodes[current_id].parent_id
            if isinstance(parent, RootParent):
                return frozenset()
            current_id = parent
        inherited = self._inherited.get(current_id, frozenset())
        if current_id != namespace_root and self._nodes[current_id].kind == NodeKind.DIRECTORY:
            inherited |= self._recursive.get(current_id, frozenset())
        for current_id in reversed(path):
            current = self._nodes[current_id]
            self._inherited[current_id] = inherited
            if current.kind == NodeKind.DIRECTORY:
                inherited |= self._recursive.get(current_id, frozenset())
        return self._inherited[node_id]


def effective_permissions(
    principals: frozenset[Principal], node_id: NodeId,
    ownerships: Iterable[Ownership], grants: Iterable[AccessGrant | AuthorizationGrant],
    nodes: Iterable[AuthorizationNode], namespaces: Iterable[NamespacePolicy],
) -> frozenset[Permission]:
    return EffectivePermissionEvaluator(principals, nodes, ownerships, grants, namespaces).permissions(node_id)


def permitted_operations(
    snapshot: FilesystemAuthorizationSnapshot, identity: ResolvedIdentity
) -> frozenset[FilesystemOperation]:
    evaluator = EffectivePermissionEvaluator(identity.principals, snapshot.nodes, snapshot.ownerships, snapshot.grants, snapshot.namespaces)
    operations: set[FilesystemOperation] = {FilesystemOperation.HOME}
    for node in snapshot.nodes:
        permissions = evaluator.permissions(node.node_id)
        if Permission.DISCOVER not in permissions:
            continue
        operations.add(FilesystemOperation.INSPECT)
        if Permission.SHARE in permissions:
            operations.add(FilesystemOperation.SHARE)
        if Permission.WRITE in permissions:
            operations.add(FilesystemOperation.UPDATE_METADATA)
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
