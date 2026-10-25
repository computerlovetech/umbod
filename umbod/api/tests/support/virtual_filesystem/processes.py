import asyncio
from pathlib import Path

from umbod.core.virtual_filesystem import NamespaceDriver, NodeKind, NodeMetadata, UnspecifiedContentType
from umbod.core.virtual_filesystem.adapters import LocalNamespace


async def create_local_child(directory: Path, name: str) -> str:
    namespace: NamespaceDriver = LocalNamespace(directory)
    root = await namespace.get_root()
    await namespace.create_node(
        root.id, name, NodeKind.FILE,
        NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
    )
    return str(root.id)


def create_local_child_in_process(directory: Path, name: str) -> str:
    return asyncio.run(create_local_child(directory, name))
