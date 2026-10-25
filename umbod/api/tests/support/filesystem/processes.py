import asyncio
from pathlib import Path

from umbod.core.filesystem import NodeKind, NodeMetadata, UnspecifiedContentType
from umbod.infrastructure import create_namespace_driver
from tests.persistence_runtime import prepared_sqlite_runtime


async def create_database_child(database_path: Path, name: str) -> str:
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        namespace = create_namespace_driver(database=runtime.database)
        root = await namespace.get_root()
        await namespace.create_node(
            root.id,
            name,
            NodeKind.FILE,
            NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
        )
        return str(root.id)
    finally:
        await runtime.shutdown()


def create_database_child_in_process(database_path: Path, name: str) -> str:
    return asyncio.run(create_database_child(database_path, name))
