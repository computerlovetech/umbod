from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from umbod.core.filesystem.browsing import (
    BrowsingExplorer, DirectoryListing, DirectoryTree, ListingLimits, NodeInspection,
    NodeTarget, PathTarget, RootTarget, Target, TreeEntry, TreeLimits,
)
from tests.umbod.core.filesystem.browsing.exploration.conftest import InMemoryBrowsing


@pytest.mark.parametrize("path", ["", "relative", "/a/./b", "/a/../b", "/a\x00", "/" + "a" * 4096, "/a" * 65])
def test_invalid_paths_are_rejected(path: str) -> None:
    with pytest.raises(ValidationError):
        PathTarget(type="path", path=path)


@pytest.mark.parametrize("path", ["/", "///", "/a//b/", "/a" * 64, "/" + "a" * 4095])
def test_valid_absolute_paths_are_preserved(path: str) -> None:
    assert PathTarget(type="path", path=path).path == path


@pytest.mark.parametrize("model", [ListingLimits, TreeLimits])
@pytest.mark.parametrize("value", [0, 1001, True, False, "1", 1.0, None])
def test_entry_limits_are_required_strict_bounded_integers(
    model: type[BaseModel], value: Any,
) -> None:
    data = {"max_entries": value}
    if model is TreeLimits:
        data["depth"] = 1
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("value", [0, 17, True, "1", 1.0, None])
def test_tree_depth_is_a_strict_bounded_integer(value: Any) -> None:
    with pytest.raises(ValidationError):
        TreeLimits(max_entries=1, depth=value)


@pytest.mark.parametrize("model", [RootTarget, PathTarget, NodeTarget, ListingLimits, TreeLimits])
def test_domain_fields_are_required(model: type[BaseModel]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({})


@pytest.mark.parametrize("field", ["size", "bytes", "policy", "permissions"])
def test_targets_and_limits_reject_incidental_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        RootTarget.model_validate({"type": "root", field: 1})
    with pytest.raises(ValidationError):
        ListingLimits.model_validate({"max_entries": 1, field: 1})


@pytest.mark.parametrize("value", ["not-a-uuid", "00000000-0000-0000-0000-000000000001", 1, None])
def test_python_node_target_requires_uuid_instance(value: Any) -> None:
    with pytest.raises(ValidationError):
        NodeTarget(type="node", node_id=value)


def test_target_union_is_discriminated_and_supports_json_uuid() -> None:
    adapter = TypeAdapter(Target)
    assert adapter.validate_json('{"type":"node","node_id":"00000000-0000-0000-0000-000000000001"}') == NodeTarget(
        type="node", node_id=UUID(int=1),
    )
    with pytest.raises(ValidationError):
        adapter.validate_python({"path": "/"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "other"})


@pytest.mark.parametrize("model", [RootTarget(type="root"), ListingLimits(max_entries=1), TreeLimits(max_entries=1000, depth=16)])
def test_models_are_frozen(model: BaseModel) -> None:
    field = next(iter(type(model).model_fields))
    with pytest.raises(ValidationError):
        setattr(model, field, getattr(model, field))


@pytest.mark.asyncio
async def test_results_expose_only_summary_and_explicit_exploration_fields(browsing: InMemoryBrowsing) -> None:
    explorer = BrowsingExplorer(browsing)
    inspection = await explorer.inspect_node(browsing.caller, RootTarget(type="root"))
    listing = await explorer.list_directory(
        browsing.caller, RootTarget(type="root"), ListingLimits(max_entries=1),
    )
    tree = await explorer.read_tree(
        browsing.caller, RootTarget(type="root"), TreeLimits(max_entries=1, depth=1),
    )
    assert set(inspection.model_dump()) == {"node", "breadcrumbs"}
    assert set(listing.model_dump()) == {"node", "breadcrumbs", "entries", "truncated"}
    assert set(tree.model_dump()) == {"node", "breadcrumbs", "entries", "expansion"}
    assert set(tree.node.model_dump()) == {
        "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision",
    }
    assert set(TreeEntry.model_fields) == {"node", "depth", "expansion"}
    for result in [inspection, listing, tree]:
        for field in ["size", "bytes", "policy", "permissions"]:
            with pytest.raises(ValidationError):
                type(result).model_validate({**result.model_dump(), field: 1})
        for field in type(result).model_fields:
            data = result.model_dump()
            del data[field]
            with pytest.raises(ValidationError):
                type(result).model_validate(data)
        with pytest.raises(ValidationError):
            result.node = browsing.root


@pytest.mark.parametrize("model", [NodeInspection, DirectoryListing, DirectoryTree, TreeEntry])
def test_results_have_strict_frozen_forbid_configuration(model: type[BaseModel]) -> None:
    assert model.model_config["strict"]
    assert model.model_config["frozen"]
    assert model.model_config["extra"] == "forbid"


def test_tree_entry_depth_and_expansion_are_required_and_strict(browsing: InMemoryBrowsing) -> None:
    for depth in [0, True, "1", 1.0, None]:
        with pytest.raises(ValidationError):
            TreeEntry(node=browsing.root, depth=depth, expansion="expanded")
    with pytest.raises(ValidationError):
        TreeEntry(node=browsing.root, depth=1, expansion="unknown")
    with pytest.raises(ValidationError):
        TreeEntry.model_validate({"node": browsing.root, "depth": 1})
