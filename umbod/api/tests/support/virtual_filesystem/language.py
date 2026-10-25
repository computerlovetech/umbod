from typing import Sequence

from .models import Metadata, NodeHandle, NodeView
from .protocols import PythonFilesystemAcceptancePort


class FilesystemDsl:
    def __init__(self, driver: PythonFilesystemAcceptancePort) -> None:
        self._driver = driver

    async def root(self) -> NodeView:
        return await self._driver.discover_root()

    async def create_directory(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView:
        return await self._driver.create_directory(parent, name, metadata)

    async def create_file(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView:
        return await self._driver.create_file(parent, name, metadata)

    async def node(self, node: NodeHandle) -> NodeView:
        return await self._driver.get_node(node)

    async def children(self, directory: NodeHandle) -> Sequence[NodeView]:
        return await self._driver.list_children(directory)

    async def read_file(self, file: NodeHandle) -> bytes:
        return await self._driver.collect(self._driver.read_content(file))

    async def write_file(self, file: NodeHandle, data: bytes, revision: int) -> NodeView:
        return await self._driver.write_content(file, self._driver.chunks(data), revision)
