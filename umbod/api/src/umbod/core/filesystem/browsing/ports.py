from collections.abc import Sequence
from typing import Protocol

from umbod.core.callers import CallerSnapshot

from ..models import NodeId
from .models import Breadcrumbs, NodeSummary


class FilesystemBrowsing(Protocol):
    async def get_breadcrumbs(self, caller: CallerSnapshot, node_id: NodeId) -> Breadcrumbs: ...

    async def get_root(self, caller: CallerSnapshot) -> NodeSummary: ...

    async def get_node(self, caller: CallerSnapshot, node_id: NodeId) -> NodeSummary: ...

    async def list_children(
        self, caller: CallerSnapshot, parent_id: NodeId
    ) -> Sequence[NodeSummary]: ...
