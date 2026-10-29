from collections.abc import Sequence

from umbod.core.callers import CallerSnapshot

from ..authorization import (
    FilesystemAuthorization, FilesystemIdentityResolver, PermissionDenied,
    UnresolvedIdentity, allows_resolved,
)
from ..errors import MissingNode, StorageFailure
from ..models import Node, NodeId, NodeKind, Permission, RootParent
from ..namespace import ROOT_ID, require_directory
from ..ports import NamespaceDriver
from ..transactions import FilesystemTransactions
from .models import BreadcrumbItem, Breadcrumbs, NodeSummary


def summary(node: Node) -> NodeSummary:
    return NodeSummary(
        id=node.id,
        parent_id=node.parent_id,
        name=node.name,
        kind=node.kind,
        metadata=node.metadata.model_copy(deep=True),
        created_at=node.created_at,
        updated_at=node.updated_at,
        revision=node.revision,
    )


def discover_denied(node_id: NodeId) -> PermissionDenied:
    return PermissionDenied(f"discover denied for node {node_id}")


class BrowsingService:
    def __init__(
        self, namespace: NamespaceDriver, authorization: FilesystemAuthorization,
        resolver: FilesystemIdentityResolver, transactions: FilesystemTransactions,
    ) -> None:
        self._namespace = namespace
        self._authorization = authorization
        self._resolver = resolver
        self._transactions = transactions

    async def get_breadcrumbs(self, caller: CallerSnapshot, node_id: NodeId) -> Breadcrumbs:
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise discover_denied(node_id)
        items: list[BreadcrumbItem] = []
        visited: set[NodeId] = set()
        current_id = node_id
        async with self._transactions.transaction() as session:
            while True:
                if current_id in visited:
                    raise StorageFailure("Invalid filesystem ancestry")
                visited.add(current_id)
                if not await allows_resolved(
                    identity, current_id, Permission.DISCOVER,
                    session.namespace, session.access_control,
                ):
                    if not items:
                        raise discover_denied(node_id)
                    return Breadcrumbs(items=list(reversed(items)), complete=False)
                try:
                    node = await session.namespace.get_node(current_id)
                except MissingNode:
                    raise StorageFailure("Invalid filesystem ancestry") from None
                if node.id != current_id or (items and node.kind != NodeKind.DIRECTORY):
                    raise StorageFailure("Invalid filesystem ancestry")
                items.append(BreadcrumbItem(id=node.id, name=node.name, kind=node.kind))
                if node.id == ROOT_ID:
                    if not isinstance(node.parent_id, RootParent) or node.kind != NodeKind.DIRECTORY or node.name != "":
                        raise StorageFailure("Invalid filesystem ancestry")
                    return Breadcrumbs(items=list(reversed(items)), complete=True)
                if isinstance(node.parent_id, RootParent):
                    raise StorageFailure("Invalid filesystem ancestry")
                current_id = node.parent_id

    async def _require_discover(self, caller: CallerSnapshot, node_id: NodeId) -> None:
        try:
            await self._authorization.require(caller, node_id, Permission.DISCOVER)
        except PermissionDenied:
            raise discover_denied(node_id) from None

    async def get_root(self, caller: CallerSnapshot) -> NodeSummary:
        try:
            root = await self._namespace.get_root()
        except MissingNode:
            raise discover_denied(ROOT_ID) from None
        await self._require_discover(caller, root.id)
        return summary(root)

    async def get_node(self, caller: CallerSnapshot, node_id: NodeId) -> NodeSummary:
        await self._require_discover(caller, node_id)
        try:
            node = await self._namespace.get_node(node_id)
        except MissingNode:
            raise discover_denied(node_id) from None
        return summary(node)

    async def list_children(
        self, caller: CallerSnapshot, parent_id: NodeId
    ) -> Sequence[NodeSummary]:
        await self._require_discover(caller, parent_id)
        try:
            parent = await self._namespace.get_node(parent_id)
            require_directory(parent)
            children = await self._namespace.list_children(parent_id)
        except MissingNode:
            raise discover_denied(parent_id) from None
        visible: list[NodeSummary] = []
        for child in children:
            try:
                await self._authorization.require(caller, child.id, Permission.DISCOVER)
            except PermissionDenied:
                continue
            visible.append(summary(child))
        return visible
