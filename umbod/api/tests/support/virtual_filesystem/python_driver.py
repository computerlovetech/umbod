from typing import Sequence
from uuid import UUID

from umbod.core.virtual_filesystem import EmptyContent, RootParent, UnspecifiedContentType

from .models import (
    ContentHandle,
    Metadata,
    MetadataValue,
    NoContentReference,
    NodeHandle,
    NodeView,
    StoredContentView,
    UntypedMetadataValue,
)
from .protocols import (
    ByteStream,
    ContentPort,
    MetadataFactory,
    NamespacePort,
    PublicFilesystem,
    PublicMetadata,
    PublicNode,
)


class DirectPythonAcceptanceDriver:
    def __init__(
        self, filesystem: PublicFilesystem, namespace: NamespacePort,
        content: ContentPort, metadata_factory: MetadataFactory,
    ) -> None:
        self._filesystem = filesystem
        self._namespace = namespace
        self._content = content
        self._metadata_factory = metadata_factory

    def _metadata(self, metadata: Metadata) -> PublicMetadata:
        content_type = (
            metadata.content_type if isinstance(metadata, MetadataValue)
            else UnspecifiedContentType()
        )
        return self._metadata_factory(
            content_type=content_type, attributes=dict(metadata.attributes),
        )

    def _view(self, node: PublicNode) -> NodeView:
        UUID(str(node.id))
        metadata: Metadata
        if isinstance(node.metadata.content_type, UnspecifiedContentType):
            metadata = UntypedMetadataValue(node.metadata.attributes)
        else:
            metadata = MetadataValue(node.metadata.content_type, node.metadata.attributes)
        return NodeView(
            node=NodeHandle(str(node.id)), name=node.name, kind=node.kind.value,
            revision=node.revision, created_at=node.created_at,
            updated_at=node.updated_at, metadata=metadata,
        )

    async def discover_root(self) -> NodeView:
        return self._view(await self._filesystem.get_root())

    async def create_directory(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView:
        return self._view(await self._filesystem.create_directory(
            UUID(parent.value), name, self._metadata(metadata),
        ))

    async def create_file(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView:
        return self._view(await self._filesystem.create_file(
            UUID(parent.value), name, self._metadata(metadata),
        ))

    async def get_node(self, node: NodeHandle) -> NodeView:
        return self._view(await self._filesystem.get_node(UUID(node.value)))

    async def list_children(self, parent: NodeHandle) -> Sequence[NodeView]:
        return tuple(self._view(node) for node in await self._filesystem.list_children(
            UUID(parent.value),
        ))

    def read_content(self, node: NodeHandle) -> ByteStream:
        return self._filesystem.read(UUID(node.value))

    async def write_content(
        self, node: NodeHandle, chunks: ByteStream, expected_revision: int,
    ) -> NodeView:
        return self._view(await self._filesystem.write(
            UUID(node.value), chunks, expected_revision=expected_revision,
        ))

    async def chunks(self, data: bytes) -> ByteStream:
        chunk_size = max(1, len(data) // 3)
        for offset in range(0, len(data), chunk_size):
            yield data[offset:offset + chunk_size]

    async def collect(self, chunks: ByteStream) -> bytes:
        return b"".join([chunk async for chunk in chunks])

    async def root_has_no_parent(self) -> bool:
        return isinstance((await self._namespace.get_root()).parent_id, RootParent)

    async def content_reference(
        self, node: NodeHandle,
    ) -> StoredContentView | NoContentReference:
        reference = (await self._namespace.get_node(UUID(node.value))).content
        if isinstance(reference, EmptyContent):
            return NoContentReference()
        return StoredContentView(ContentHandle(reference.key), reference.size)

    async def stored_bytes(self, content: ContentHandle) -> bytes:
        return await self.collect(self._content.get(content.value))
