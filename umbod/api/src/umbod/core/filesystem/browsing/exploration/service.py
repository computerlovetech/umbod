from typing import Literal

from umbod.core.callers import CallerSnapshot

from ...authorization import PermissionDenied
from ...errors import StorageFailure, WrongNodeKind
from ...models import NodeId, NodeKind
from ..models import NodeSummary
from ..ports import FilesystemBrowsing
from .models import (
    DirectoryListing, DirectoryTree, ListingLimits, NodeInspection, NodeTarget,
    PathTarget, Target, TreeEntry, TreeLimits,
)


def require_directory(node: NodeSummary) -> None:
    if node.kind != NodeKind.DIRECTORY:
        raise WrongNodeKind(str(node.id))


def child_order(node: NodeSummary) -> tuple[bool, str, str, str]:
    return node.kind != NodeKind.DIRECTORY, node.name.casefold(), node.name, str(node.id)


class BrowsingExplorer:
    def __init__(self, browsing: FilesystemBrowsing) -> None:
        self._browsing = browsing

    async def _resolve(self, caller: CallerSnapshot, target: Target) -> NodeSummary:
        if isinstance(target, NodeTarget):
            return await self._browsing.get_node(caller, target.node_id)
        node = await self._browsing.get_root(caller)
        if isinstance(target, PathTarget):
            visited = {node.id}
            for segment in filter(None, target.path.split("/")):
                require_directory(node)
                children = await self._children(caller, node, visited)
                matches = [child for child in children if child.name == segment]
                if not matches:
                    raise PermissionDenied("Filesystem path is unavailable")
                if len(matches) != 1:
                    raise StorageFailure("Invalid filesystem hierarchy")
                node = matches[0]
        return node

    async def _children(
        self, caller: CallerSnapshot, node: NodeSummary, visited: set[NodeId]
    ) -> list[NodeSummary]:
        children = list(await self._browsing.list_children(caller, node.id))
        for child in children:
            if child.id in visited:
                raise StorageFailure("Invalid filesystem hierarchy")
            visited.add(child.id)
        return sorted(children, key=child_order)

    async def inspect_node(self, caller: CallerSnapshot, target: Target) -> NodeInspection:
        node = await self._resolve(caller, target)
        breadcrumbs = await self._browsing.get_breadcrumbs(caller, node.id)
        return NodeInspection(node=node, breadcrumbs=breadcrumbs)

    async def list_directory(
        self, caller: CallerSnapshot, target: Target, limits: ListingLimits
    ) -> DirectoryListing:
        inspection = await self.inspect_node(caller, target)
        require_directory(inspection.node)
        children = await self._children(caller, inspection.node, {inspection.node.id})
        return DirectoryListing(
            node=inspection.node, breadcrumbs=inspection.breadcrumbs,
            entries=children[:limits.max_entries], truncated=len(children) > limits.max_entries,
        )

    async def read_tree(
        self, caller: CallerSnapshot, target: Target, limits: TreeLimits
    ) -> DirectoryTree:
        inspection = await self.inspect_node(caller, target)
        require_directory(inspection.node)
        entries: list[TreeEntry] = []
        visited = {inspection.node.id}
        expansion = await self._expand(caller, inspection.node, 0, limits, entries, visited)
        return DirectoryTree(
            node=inspection.node, breadcrumbs=inspection.breadcrumbs,
            entries=entries, expansion=expansion,
        )

    async def _expand(
        self, caller: CallerSnapshot, node: NodeSummary, depth: int,
        limits: TreeLimits, entries: list[TreeEntry], visited: set[NodeId],
    ) -> Literal["expanded", "entry_limit"]:
        children = await self._children(caller, node, visited)
        for child in children:
            if len(entries) == limits.max_entries:
                return "entry_limit"
            entry_depth = depth + 1
            position = len(entries)
            expansion: Literal["file", "expanded", "depth_limit", "entry_limit"] = "file"
            if child.kind == NodeKind.DIRECTORY:
                expansion = "depth_limit" if entry_depth == limits.depth else "entry_limit"
            entries.append(TreeEntry(node=child, depth=entry_depth, expansion=expansion))
            if child.kind == NodeKind.DIRECTORY and entry_depth < limits.depth:
                if len(entries) < limits.max_entries:
                    expansion = await self._expand(
                        caller, child, entry_depth, limits, entries, visited,
                    )
                    entries[position] = TreeEntry(
                        node=child, depth=entry_depth, expansion=expansion,
                    )
        return "expanded"
