from typing import Protocol

from umbod.core.callers import CallerSnapshot

from .models import (
    DirectoryListing, DirectoryTree, ListingLimits, NodeInspection, Target, TreeLimits,
)


class FilesystemExplorer(Protocol):
    async def inspect_node(self, caller: CallerSnapshot, target: Target) -> NodeInspection: ...

    async def list_directory(
        self, caller: CallerSnapshot, target: Target, limits: ListingLimits
    ) -> DirectoryListing: ...

    async def read_tree(
        self, caller: CallerSnapshot, target: Target, limits: TreeLimits
    ) -> DirectoryTree: ...
