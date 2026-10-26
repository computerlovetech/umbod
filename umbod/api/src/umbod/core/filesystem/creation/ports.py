from typing import Protocol

from umbod.core.callers import CallerSnapshot

from ..browsing import NodeSummary
from ..models import NodeId, NodeMetadata


class FilesystemCreation(Protocol):
    async def create_file(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str, metadata: NodeMetadata
    ) -> NodeSummary: ...

    async def create_directory(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str, metadata: NodeMetadata
    ) -> NodeSummary: ...
