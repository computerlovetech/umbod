import asyncio
from pathlib import Path

import pytest

from umbod.core.filesystem import NodeKind, NodeMetadata
from umbod.core.persistence import TransactionMode
from umbod.infrastructure import create_namespace_driver
from tests.persistence_runtime import prepared_sqlite_runtime


@pytest.mark.asyncio
async def test_initialized_namespace_reads_do_not_acquire_shared_database_writer_lock(
    tmp_path: Path,
) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "reads.db")
    try:
        namespace = create_namespace_driver(database=runtime.database)
        root = await namespace.get_root()
        file = await namespace.create_node(
            root.id, "retained", NodeKind.FILE,
            NodeMetadata(content_type="text/plain", attributes={}),
        )
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE):
            observed_root, observed_file, children = await asyncio.wait_for(
                asyncio.gather(
                    namespace.get_root(), namespace.get_node(file.id),
                    namespace.list_children(root.id),
                ), timeout=2,
            )
        assert observed_root == root
        assert observed_file == file
        assert tuple(children) == (file,)
    finally:
        await runtime.shutdown()
