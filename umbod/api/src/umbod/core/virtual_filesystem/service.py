from collections.abc import Sequence

from .errors import WrongNodeKind
from .models import EmptyContent, Node, NodeId, NodeKind, NodeMetadata
from .ports import ByteStream, ContentDriver, NamespaceDriver


class VirtualFilesystem:
    def __init__(self, *, namespace: NamespaceDriver, content: ContentDriver) -> None:
        self._namespace = namespace
        self._content = content

    async def get_root(self) -> Node:
        return await self._namespace.get_root()

    async def create_directory(
        self, parent_id: NodeId, name: str, metadata: NodeMetadata,
    ) -> Node:
        return await self._namespace.create_node(
            parent_id, name, NodeKind.DIRECTORY, metadata,
        )

    async def create_file(
        self, parent_id: NodeId, name: str, metadata: NodeMetadata,
    ) -> Node:
        return await self._namespace.create_node(
            parent_id, name, NodeKind.FILE, metadata,
        )

    async def get_node(self, node_id: NodeId) -> Node:
        return await self._namespace.get_node(node_id)

    async def list_children(self, parent_id: NodeId) -> Sequence[Node]:
        return await self._namespace.list_children(parent_id)

    async def write(
        self, node_id: NodeId, data: ByteStream, *, expected_revision: int,
    ) -> Node:
        node = await self._namespace.get_node(node_id)
        if node.kind != NodeKind.FILE:
            raise WrongNodeKind(str(node_id))
        content = await self._content.put(data)
        return await self._namespace.update_node(
            node_id, content=content, expected_revision=expected_revision,
        )

    async def read(self, node_id: NodeId) -> ByteStream:
        node = await self._namespace.get_node(node_id)
        if node.kind != NodeKind.FILE:
            raise WrongNodeKind(str(node_id))
        if isinstance(node.content, EmptyContent):
            return
        async for chunk in self._content.get(node.content.key):
            yield chunk
