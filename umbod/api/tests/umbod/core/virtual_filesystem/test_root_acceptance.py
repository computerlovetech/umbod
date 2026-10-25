import pytest

from tests.support.virtual_filesystem import FilesystemAcceptanceContext


@pytest.mark.asyncio
async def test_callers_discover_the_same_driver_provided_root(
    filesystem_context: FilesystemAcceptanceContext,
) -> None:
    first = await filesystem_context.filesystem.root()
    second = await filesystem_context.other_caller.root()

    assert first.node == second.node == filesystem_context.supplied_root
    assert first.kind == second.kind == "directory"
    assert first.name == second.name == ""
    assert await filesystem_context.observations.root_has_no_parent()
    assert filesystem_context.namespace_evidence.root_count == 1
    assert filesystem_context.namespace_evidence.creation_calls == 0
