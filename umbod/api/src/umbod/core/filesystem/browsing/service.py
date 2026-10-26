from collections.abc import Sequence

from umbod.core.callers import CallerSnapshot

from ..authorization import FilesystemAuthorization, PermissionDenied
from ..errors import MissingNode
from ..models import Node, NodeId, Permission
from ..namespace import ROOT_ID, require_directory
from ..ports import NamespaceDriver
from .models import NodeSummary


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
        self, namespace: NamespaceDriver, authorization: FilesystemAuthorization
    ) -> None:
        self._namespace = namespace
        self._authorization = authorization

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
