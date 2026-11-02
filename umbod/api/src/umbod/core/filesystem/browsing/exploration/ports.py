from typing import Protocol

from umbod.core.callers import CallerSnapshot

from ...authorization import ResolvedIdentity
from ...models import NodeId
from .models import (
    BrowseResult, BrowseScope,
    DirectoryListing, DirectoryTree, ListingLimits, NodeInspection, Target, TreeLimits,
)


class BrowseScopeReader(Protocol):
    async def read_scope(self, node_id: NodeId, identity: ResolvedIdentity) -> BrowseScope: ...


class FilesystemBrowser(Protocol):
    async def browse_node(self, caller: CallerSnapshot, node_id: NodeId) -> BrowseResult: ...


class FilesystemExplorer(Protocol):
    async def inspect_node(self, caller: CallerSnapshot, target: Target) -> NodeInspection: ...

    async def list_directory(
        self, caller: CallerSnapshot, target: Target, limits: ListingLimits
    ) -> DirectoryListing: ...

    async def read_tree(
        self, caller: CallerSnapshot, target: Target, limits: TreeLimits
    ) -> DirectoryTree: ...
