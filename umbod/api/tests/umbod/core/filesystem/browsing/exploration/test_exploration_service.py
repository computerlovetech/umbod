from uuid import UUID

import pytest

from tests.umbod.core.filesystem.browsing.exploration.conftest import InMemoryBrowsing
from umbod.core.filesystem import NodeKind, StorageFailure, WrongNodeKind
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing import (
    BrowsingExplorer, FilesystemExplorer, ListingLimits, NodeTarget, PathTarget, RootTarget,
    TreeLimits,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("target", [RootTarget(type="root"), PathTarget(type="path", path="///")])
async def test_inspect_root_does_not_list_children(
    browsing: InMemoryBrowsing, target: RootTarget | PathTarget,
) -> None:
    explorer: FilesystemExplorer = BrowsingExplorer(browsing)
    result = await explorer.inspect_node(browsing.caller, target)
    assert result.node == browsing.root
    assert result.breadcrumbs.complete
    assert browsing.calls == [("root", browsing.root.id), ("breadcrumbs", browsing.root.id)]


async def test_path_resolution_uses_visible_children_and_preserves_partial_breadcrumbs(
    browsing: InMemoryBrowsing,
) -> None:
    directory = browsing.add(1, "Documents", NodeKind.DIRECTORY, browsing.root)
    file = browsing.add(2, "File", NodeKind.FILE, directory)
    result = await BrowsingExplorer(browsing).inspect_node(
        browsing.caller, PathTarget(type="path", path="//Documents///File/"),
    )
    assert result.node == file
    assert not result.breadcrumbs.complete
    assert [item.id for item in result.breadcrumbs.items] == [file.id]
    assert browsing.calls == [
        ("root", browsing.root.id), ("children", browsing.root.id),
        ("children", directory.id), ("breadcrumbs", file.id),
    ]


async def test_node_inspection_needs_no_root_or_ancestor_access(browsing: InMemoryBrowsing) -> None:
    directory = browsing.add(1, "secret", NodeKind.DIRECTORY, browsing.root)
    file = browsing.add(2, "shared", NodeKind.FILE, directory)
    browsing.hidden.update({browsing.root.id, directory.id})
    result = await BrowsingExplorer(browsing).inspect_node(
        browsing.caller, NodeTarget(type="node", node_id=file.id),
    )
    assert result.node == file
    assert not result.breadcrumbs.complete
    assert browsing.calls == [("node", file.id), ("breadcrumbs", file.id)]


@pytest.mark.parametrize("hidden", [False, True])
async def test_missing_and_hidden_paths_are_permission_denied(
    browsing: InMemoryBrowsing, hidden: bool,
) -> None:
    if hidden:
        file = browsing.add(1, "unavailable", NodeKind.FILE, browsing.root)
        browsing.hidden.add(file.id)
    with pytest.raises(PermissionDenied):
        await BrowsingExplorer(browsing).inspect_node(
            browsing.caller, PathTarget(type="path", path="/unavailable"),
        )


@pytest.mark.parametrize("hidden", [False, True])
async def test_missing_and_hidden_node_ids_are_permission_denied(
    browsing: InMemoryBrowsing, hidden: bool,
) -> None:
    if hidden:
        file = browsing.add(1, "unavailable", NodeKind.FILE, browsing.root)
        browsing.hidden.add(file.id)
    with pytest.raises(PermissionDenied):
        await BrowsingExplorer(browsing).inspect_node(
            browsing.caller, NodeTarget(type="node", node_id=UUID(int=1)),
        )


@pytest.mark.parametrize("operation", ["path", "list", "tree"])
async def test_file_as_traversed_directory_raises_wrong_node_kind(
    browsing: InMemoryBrowsing, operation: str,
) -> None:
    file = browsing.add(1, "file", NodeKind.FILE, browsing.root)
    explorer = BrowsingExplorer(browsing)
    target = NodeTarget(type="node", node_id=file.id)
    with pytest.raises(WrongNodeKind):
        if operation == "path":
            await explorer.inspect_node(browsing.caller, PathTarget(type="path", path="/file/child"))
        elif operation == "list":
            await explorer.list_directory(browsing.caller, target, ListingLimits(max_entries=10))
        else:
            await explorer.read_tree(browsing.caller, target, TreeLimits(max_entries=10, depth=2))
    assert ("children", file.id) not in browsing.calls


@pytest.mark.parametrize("limit,truncated", [(1, True), (5, False), (10, False)])
async def test_directory_listing_has_total_order_and_exact_truncation(
    browsing: InMemoryBrowsing, limit: int, truncated: bool,
) -> None:
    file = browsing.add(5, "A", NodeKind.FILE, browsing.root)
    lower = browsing.add(4, "a", NodeKind.DIRECTORY, browsing.root)
    higher_id = browsing.add(3, "A", NodeKind.DIRECTORY, browsing.root)
    lower_id = browsing.add(2, "A", NodeKind.DIRECTORY, browsing.root)
    last = browsing.add(6, "z", NodeKind.FILE, browsing.root)
    hidden = browsing.add(7, "hidden", NodeKind.FILE, browsing.root)
    browsing.hidden.add(hidden.id)
    result = await BrowsingExplorer(browsing).list_directory(
        browsing.caller, RootTarget(type="root"), ListingLimits(max_entries=limit),
    )
    assert result.entries == [lower_id, higher_id, lower, file, last][:limit]
    assert result.truncated is truncated


async def test_tree_depth_limit_does_not_list_unexpanded_directories(browsing: InMemoryBrowsing) -> None:
    directory = browsing.add(1, "directory", NodeKind.DIRECTORY, browsing.root)
    browsing.add(2, "deeper", NodeKind.FILE, directory)
    file = browsing.add(3, "file", NodeKind.FILE, browsing.root)
    result = await BrowsingExplorer(browsing).read_tree(
        browsing.caller, RootTarget(type="root"), TreeLimits(max_entries=1000, depth=1),
    )
    assert result.expansion == "expanded"
    assert [(entry.node.id, entry.depth, entry.expansion) for entry in result.entries] == [
        (directory.id, 1, "depth_limit"), (file.id, 1, "file"),
    ]
    assert ("children", directory.id) not in browsing.calls


@pytest.mark.parametrize(
    "budget,expected,root_expansion",
    [
        (1, [(1, 1, "entry_limit")], "entry_limit"),
        (2, [(1, 1, "entry_limit"), (2, 2, "file")], "entry_limit"),
        (3, [(1, 1, "expanded"), (2, 2, "file"), (3, 2, "file")], "entry_limit"),
        (4, [(1, 1, "expanded"), (2, 2, "file"), (3, 2, "file"), (4, 1, "file")], "expanded"),
    ],
)
async def test_tree_budget_is_global_depth_first_and_excludes_selected_node(
    browsing: InMemoryBrowsing, budget: int,
    expected: list[tuple[int, int, str]], root_expansion: str,
) -> None:
    directory = browsing.add(1, "directory", NodeKind.DIRECTORY, browsing.root)
    browsing.add(3, "b", NodeKind.FILE, directory)
    browsing.add(2, "a", NodeKind.FILE, directory)
    browsing.add(4, "z", NodeKind.FILE, browsing.root)
    result = await BrowsingExplorer(browsing).read_tree(
        browsing.caller, RootTarget(type="root"), TreeLimits(max_entries=budget, depth=16),
    )
    assert [(entry.node.id.int, entry.depth, entry.expansion) for entry in result.entries] == expected
    assert result.expansion == root_expansion
    assert len(result.entries) <= budget


async def test_tree_nested_directory_at_depth_limit_is_not_expanded(browsing: InMemoryBrowsing) -> None:
    parent = browsing.add(1, "parent", NodeKind.DIRECTORY, browsing.root)
    child = browsing.add(2, "child", NodeKind.DIRECTORY, parent)
    browsing.add(3, "leaf", NodeKind.FILE, child)
    result = await BrowsingExplorer(browsing).read_tree(
        browsing.caller, RootTarget(type="root"), TreeLimits(max_entries=10, depth=2),
    )
    assert [(entry.depth, entry.expansion) for entry in result.entries] == [
        (1, "expanded"), (2, "depth_limit"),
    ]
    assert ("children", child.id) not in browsing.calls


async def test_empty_tree_has_expanded_root(browsing: InMemoryBrowsing) -> None:
    result = await BrowsingExplorer(browsing).read_tree(
        browsing.caller, RootTarget(type="root"), TreeLimits(max_entries=1, depth=1),
    )
    assert result.entries == []
    assert result.expansion == "expanded"


@pytest.mark.parametrize("operation", ["path", "tree", "list"])
@pytest.mark.parametrize("corruption", ["cycle", "duplicate"])
async def test_repeated_ids_fail_without_looping(
    browsing: InMemoryBrowsing, operation: str, corruption: str,
) -> None:
    directory = browsing.add(1, "directory", NodeKind.DIRECTORY, browsing.root)
    if corruption == "cycle":
        browsing.children[browsing.root.id].append(browsing.root)
    else:
        browsing.children[browsing.root.id].append(directory)
    explorer = BrowsingExplorer(browsing)
    with pytest.raises(StorageFailure):
        if operation == "path":
            await explorer.inspect_node(browsing.caller, PathTarget(type="path", path="/directory"))
        elif operation == "list":
            await explorer.list_directory(browsing.caller, RootTarget(type="root"), ListingLimits(max_entries=1))
        else:
            await explorer.read_tree(browsing.caller, RootTarget(type="root"), TreeLimits(max_entries=10, depth=16))


async def test_repeated_ids_across_branches_fail(browsing: InMemoryBrowsing) -> None:
    first = browsing.add(1, "a", NodeKind.DIRECTORY, browsing.root)
    second = browsing.add(2, "b", NodeKind.DIRECTORY, browsing.root)
    file = browsing.add(3, "shared", NodeKind.FILE, first)
    browsing.children[second.id].append(file)
    with pytest.raises(StorageFailure):
        await BrowsingExplorer(browsing).read_tree(
            browsing.caller, RootTarget(type="root"), TreeLimits(max_entries=10, depth=16),
        )


async def test_path_cycle_after_first_segment_fails(browsing: InMemoryBrowsing) -> None:
    directory = browsing.add(1, "directory", NodeKind.DIRECTORY, browsing.root)
    browsing.children[directory.id].append(directory)
    with pytest.raises(StorageFailure):
        await BrowsingExplorer(browsing).inspect_node(
            browsing.caller, PathTarget(type="path", path="/directory/directory"),
        )
