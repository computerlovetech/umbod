from collections.abc import Sequence
from typing import Protocol

from umbod.core.callers import CallerContext

from ..models import NodeId
from .models import NodeSummary


class FilesystemBrowsing(Protocol):
    async def get_root(self, caller: CallerContext) -> NodeSummary: ...

    async def get_node(self, caller: CallerContext, node_id: NodeId) -> NodeSummary: ...

    async def list_children(
        self, caller: CallerContext, parent_id: NodeId
    ) -> Sequence[NodeSummary]: ...
