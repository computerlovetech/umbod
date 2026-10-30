from asyncio import Lock
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from umbod.core.groups.models import Group
from umbod.core.filesystem import (
    AccessControlDriver, AccessGrant, ContentRef, MissingNode, NamespaceDriver,
    Node, NodeId, NodeKind, NodeMetadata, Ownership, OwnershipNotFound, Principal,
)
from umbod.core.filesystem.sharing.ports import (
    RegisteredGroupReader, SharingGrantWriter, SharingSession,
)


class SharingNamespace:
    def __init__(self, nodes: tuple[Node, ...]) -> None:
        self.nodes = {node.id: node for node in nodes}

    async def get_node(self, node_id: NodeId) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as error:
            raise MissingNode() from error

    async def get_root(self) -> Node:
        raise NotImplementedError()

    async def list_children(self, parent_id: NodeId) -> list[Node]:
        return [node for node in self.nodes.values() if node.parent_id == parent_id]

    async def create_node(
        self, parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata,
    ) -> Node:
        raise NotImplementedError()

    async def update_node(
        self, node_id: NodeId, *, content: ContentRef, expected_revision: int,
    ) -> Node:
        raise NotImplementedError()

    async def delete_node(self, node_id: NodeId, *, expected_revision: int) -> None:
        raise NotImplementedError()


class SharingPolicies:
    def __init__(self, ownership: Ownership, grants: tuple[AccessGrant, ...]) -> None:
        self.owners = {ownership.node_id: ownership}
        self.grants = {(grant.node_id, grant.principal): grant for grant in grants}

    async def get_owner(self, node_id: NodeId) -> Ownership:
        try:
            return self.owners[node_id]
        except KeyError as error:
            raise OwnershipNotFound() from error

    async def set_owner(self, ownership: Ownership) -> None:
        self.owners[ownership.node_id] = ownership

    async def list_grants(self, node_id: NodeId) -> list[AccessGrant]:
        return [grant for grant in self.grants.values() if grant.node_id == node_id]

    async def add_grant(self, grant: AccessGrant) -> None:
        await self.upsert(grant)

    async def upsert(self, grant: AccessGrant) -> None:
        self.grants[grant.node_id, grant.principal] = grant.model_copy(deep=True)

    async def remove_grant(self, node_id: NodeId, principal: Principal) -> None:
        self.grants.pop((node_id, principal), None)

    async def clear_node(self, node_id: NodeId) -> None:
        self.owners.pop(node_id, None)
        self.grants = {key: grant for key, grant in self.grants.items() if key[0] != node_id}


class SharingGroups:
    def __init__(self, identifiers: frozenset[str]) -> None:
        self.identifiers = identifiers
        self.reads = 0

    async def registered_groups(self) -> tuple[Group, ...]:
        self.reads += 1
        return tuple(
            Group(group_id=value, label=value, description="", revision=1)
            for value in self.identifiers
        )

    async def registered_group_ids(self) -> frozenset[str]:
        self.reads += 1
        return self.identifiers


@dataclass(frozen=True)
class InMemorySharingSession:
    namespace: NamespaceDriver
    access_control: AccessControlDriver
    groups: RegisteredGroupReader
    grants: SharingGrantWriter


class InMemorySharingTransactions:
    def __init__(
        self, namespace: SharingNamespace, policies: SharingPolicies, groups: SharingGroups,
    ) -> None:
        self.namespace = namespace
        self.policies = policies
        self.groups = groups
        self._lock = Lock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SharingSession]:
        async with self._lock:
            previous = self.policies.grants.copy()
            try:
                yield InMemorySharingSession(
                    namespace=self.namespace, access_control=self.policies,
                    groups=self.groups, grants=self.policies,
                )
            except BaseException:
                self.policies.grants = previous
                raise
