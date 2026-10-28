from typing import Protocol

from umbod.core.callers import CallerSnapshot

from ..browsing import NodeSummary
from ..models import NodeId, NodeMetadata
from ..ports import ByteStream
from .models import ContentDownload


class FilesystemContent(Protocol):
    async def authorize_upload(self, snapshot: CallerSnapshot, parent_id: NodeId) -> None: ...

    async def upload(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str,
        metadata: NodeMetadata, data: ByteStream,
    ) -> NodeSummary: ...

    async def open_download(
        self, snapshot: CallerSnapshot, node_id: NodeId,
    ) -> ContentDownload: ...
