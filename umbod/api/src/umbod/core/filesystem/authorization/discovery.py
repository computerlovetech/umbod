from collections.abc import Iterable
from enum import StrEnum
from typing import Self, Union

from pydantic import BaseModel, ConfigDict, model_validator

from ..models import AccessGrant, NodeId, NodeKind, Ownership, Permission, Principal
from ..namespace import ROOT_ID
from .models import ResolvedIdentity


FILESYSTEM_DISCOVERY_CHANGED = "filesystem.discovery_changed"


class FilesystemOperation(StrEnum):
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

def effective_permissions(
    principals: frozenset[Principal],
    node_id: NodeId,
    ownerships: tuple[Ownership, ...],
    grants: Iterable[Union[AccessGrant, AuthorizationGrant]],
) -> frozenset[Permission]:
    owners = tuple(owner for owner in ownerships if owner.node_id == node_id)
    if not owners:
        return frozenset()
    if any(owner.owner in principals for owner in owners):
        return frozenset(Permission)
    return frozenset(
        permission
        for grant in grants
        if grant.node_id == node_id and grant.principal in principals
        for permission in grant.permissions
    )


def permitted_operations(
    snapshot: FilesystemAuthorizationSnapshot, identity: ResolvedIdentity
) -> frozenset[FilesystemOperation]:
    ownerships = {ownership.node_id: (ownership,) for ownership in snapshot.ownerships}
    grants: dict[NodeId, list[AuthorizationGrant]] = {}
    for grant in snapshot.grants:
        grants.setdefault(grant.node_id, []).append(grant)
    principals = identity.principals
    operations: set[FilesystemOperation] = set()
    for node in snapshot.nodes:
        permissions = effective_permissions(
            principals, node.node_id, ownerships.get(node.node_id, ()),
            grants.get(node.node_id, ()),
        )
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
