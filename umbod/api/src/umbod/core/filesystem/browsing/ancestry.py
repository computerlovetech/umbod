from collections.abc import Awaitable, Callable
from typing import Optional

from ..errors import StorageFailure
from ..models import NodeId, NodeKind, RootParent
from ..namespace import ROOT_ID
from .models import BreadcrumbItem, Breadcrumbs, NodeSummary
from ..authorization import PermissionDenied


async def discoverable_breadcrumbs(
    node_id: NodeId, discover: Callable[[NodeId], Awaitable[Optional[NodeSummary]]],
) -> Breadcrumbs:
    items: list[BreadcrumbItem] = []
    visited: set[NodeId] = set()
    current_id = node_id
    while True:
        if current_id in visited:
            raise StorageFailure("Invalid filesystem ancestry")
        visited.add(current_id)
        node = await discover(current_id)
        if node is None:
            if not items:
                raise PermissionDenied(f"discover denied for node {node_id}")
            return Breadcrumbs(items=list(reversed(items)), complete=False)
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
