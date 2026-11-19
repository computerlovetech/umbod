from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from .namespaces.models import NamespacePolicy
from .models import (
    AccessGrant,
    Ownership,
    Principal,
    ContentRef,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
    NodeUpdate,
    StorageKey,
)

ByteStream = AsyncIterator[bytes]


class NodeReader(Protocol):
    async def get_node(self, node_id: NodeId) -> Node: ...


class NamespaceDriver(NodeReader, Protocol):
    async def get_root(self) -> Node: ...
    async def list_children(self, parent_id: NodeId) -> Sequence[Node]: ...
    async def create_node(
        self,
        parent_id: NodeId,
        name: str,
        kind: NodeKind,
        metadata: NodeMetadata,
    ) -> Node: ...
    async def update_node(
        self,
        node_id: NodeId,
        *,
        content: ContentRef,
        expected_revision: int,
    ) -> Node: ...
    async def update_metadata(
        self, node_id: NodeId, *, metadata: NodeMetadata, expected_revision: int,
    ) -> Node: ...
    async def update_details(
        self, node_id: NodeId, *, details: NodeUpdate, expected_revision: int,
    ) -> Node: ...
    async def delete_node(self, node_id: NodeId, *, expected_revision: int) -> None: ...


class AccessControlReader(Protocol):
    async def list_namespace_policies(self) -> list[NamespacePolicy]: ...
    async def get_owner(self, node_id: NodeId) -> Ownership: ...
    async def list_grants(self, node_id: NodeId) -> Sequence[AccessGrant]: ...
    async def list_granted_node_ids(self, principals: frozenset[Principal]) -> frozenset[NodeId]: ...


class AccessControlDriver(AccessControlReader, Protocol):
    async def set_owner(self, ownership: Ownership) -> None: ...
    async def add_grant(self, grant: AccessGrant) -> None: ...
    async def remove_grant(self, node_id: NodeId, principal: Principal) -> None: ...
    async def clear_node(self, node_id: NodeId) -> None: ...


class ContentDriver(Protocol):
    async def put(self, data: ByteStream) -> ContentRef: ...
    def get(self, key: StorageKey) -> ByteStream: ...
