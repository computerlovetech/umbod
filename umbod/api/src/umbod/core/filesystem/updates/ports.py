from typing import Protocol

from umbod.core.callers import CallerSnapshot

from ..browsing import NodeSummary
from ..models import NodeId
from .models import NodePatch


class FilesystemNodeUpdates(Protocol):
    async def check_update_eligibility(self, snapshot: CallerSnapshot, node_id: NodeId) -> None: ...

    async def update_node(
        self, snapshot: CallerSnapshot, node_id: NodeId, patch: NodePatch, *, expected_revision: int,
    ) -> NodeSummary: ...
