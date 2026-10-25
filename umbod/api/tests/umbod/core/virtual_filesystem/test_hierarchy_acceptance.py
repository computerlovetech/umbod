from datetime import datetime
from uuid import UUID

import pytest

from tests.support.virtual_filesystem import (
    FilesystemAcceptanceContext,
    MetadataValue,
    UntypedMetadataValue,
)


@pytest.mark.asyncio
async def test_created_nodes_form_a_retrievable_nested_hierarchy(
    filesystem_context: FilesystemAcceptanceContext,
) -> None:
    filesystem = filesystem_context.filesystem
    root = await filesystem.root()
    directory_metadata = UntypedMetadataValue({"purpose": "reports", "team": "research"})
    file_metadata = MetadataValue("text/plain", {"language": "en", "status": "draft"})

    directory = await filesystem.create_directory(root.node, "Reports", directory_metadata)
    file = await filesystem.create_file(directory.node, "results.txt", file_metadata)

    assert len({UUID(root.node.value), UUID(directory.node.value), UUID(file.node.value)}) == 3
    assert directory.name == "Reports"
    assert directory.kind == "directory"
    assert directory.metadata == directory_metadata
    assert file.name == "results.txt"
    assert file.kind == "file"
    assert file.metadata == file_metadata
    assert await filesystem.node(directory.node) == directory
    assert await filesystem.node(file.node) == file
    assert tuple(await filesystem.children(root.node)) == (directory,)
    assert tuple(await filesystem.children(directory.node)) == (file,)
    for node in (directory, file):
        assert node.revision > 0
        assert isinstance(node.created_at, datetime)
        assert isinstance(node.updated_at, datetime)
        assert node.updated_at >= node.created_at
