from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from unittest.mock import Mock, call, create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import MissingNode, NamespaceDriver, Node, Permission, StorageFailure
from umbod.core.filesystem.authorization import FilesystemAuthorization, PermissionDenied
from umbod.core.filesystem.browsing import BrowsingService, FilesystemBrowsing, NodeSummary
from umbod.core.filesystem.namespace import initial_root
from tests.support.filesystem.authorization import caller


@dataclass(frozen=True)
class BrowsingMocks:
    browsing: FilesystemBrowsing
    namespace: Mock
    authorization: Mock
    root: Node


@pytest.fixture
def browsing_mocks() -> BrowsingMocks:
    namespace = create_autospec(NamespaceDriver, instance=True, spec_set=True)
    authorization = create_autospec(FilesystemAuthorization, instance=True, spec_set=True)
    root = initial_root()
    namespace.get_root.return_value = root
    namespace.get_node.return_value = root
    namespace.list_children.return_value = []
    browsing: FilesystemBrowsing = BrowsingService(
        cast(NamespaceDriver, namespace), cast(FilesystemAuthorization, authorization)
    )
    return BrowsingMocks(browsing, namespace, authorization, root)


async def observe(context: BrowsingMocks, operation: str) -> Sequence[NodeSummary]:
    if operation == "root":
        return [await context.browsing.get_root(caller("alice"))]
    if operation == "node":
        return [await context.browsing.get_node(caller("alice"), context.root.id)]
    return await context.browsing.list_children(caller("alice"), context.root.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["root", "node", "list"])
async def test_browsing_uses_only_discover_and_necessary_namespace_reads(
    browsing_mocks: BrowsingMocks, operation: str,
) -> None:
    context = browsing_mocks
    result = await observe(context, operation)
    assert len(result) == (0 if operation == "list" else 1)
    assert context.authorization.mock_calls == [call.require(caller("alice"), context.root.id, Permission.DISCOVER)]
    expected = {
        "root": [call.get_root()],
        "node": [call.get_node(context.root.id)],
        "list": [call.get_node(context.root.id), call.list_children(context.root.id)],
    }
    assert context.namespace.mock_calls == expected[operation]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["node", "list"])
async def test_denied_targets_do_not_trigger_namespace_or_ancestor_reads(
    browsing_mocks: BrowsingMocks, operation: str,
) -> None:
    context = browsing_mocks
    context.authorization.require.side_effect = PermissionDenied("sensitive identity or storage detail")
    with pytest.raises(PermissionDenied, match=f"^discover denied for node {context.root.id}$") as caught:
        await observe(context, operation)
    assert caught.value.__suppress_context__
    assert "sensitive" not in str(caught.value)
    assert context.namespace.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_read", ["get_root", "get_node", "list_children"])
@pytest.mark.parametrize("failure_type", [MissingNode, StorageFailure, RuntimeError])
async def test_namespace_absence_is_uniform_denial_and_other_failures_propagate(
    browsing_mocks: BrowsingMocks, failing_read: str, failure_type: type[Exception],
) -> None:
    context = browsing_mocks
    failure = failure_type("backend detail")
    getattr(context.namespace, failing_read).side_effect = failure
    operation = {"get_root": "root", "get_node": "node", "list_children": "list"}[failing_read]
    with pytest.raises(PermissionDenied if failure_type is MissingNode else failure_type) as caught:
        await observe(context, operation)
    if failure_type is MissingNode:
        assert str(caught.value) == f"discover denied for node {context.root.id}"
        assert caught.value.__suppress_context__
    else:
        assert caught.value is failure


@pytest.mark.asyncio
async def test_root_authorization_denial_suppresses_injected_sensitive_details(
    browsing_mocks: BrowsingMocks,
) -> None:
    context = browsing_mocks
    context.authorization.require.side_effect = PermissionDenied("sensitive root policy detail")
    with pytest.raises(PermissionDenied, match=f"^discover denied for node {context.root.id}$") as caught:
        await context.browsing.get_root(caller("alice"))
    assert caught.value.__suppress_context__
    assert "sensitive" not in str(caught.value)
    assert context.namespace.mock_calls == [call.get_root()]


@pytest.mark.asyncio
async def test_parent_disappearing_after_authorization_is_uniform_denial(
    browsing_mocks: BrowsingMocks,
) -> None:
    context = browsing_mocks
    context.namespace.get_node.side_effect = MissingNode("private storage detail")
    with pytest.raises(PermissionDenied, match=f"^discover denied for node {context.root.id}$"):
        await context.browsing.list_children(caller("alice"), context.root.id)
    context.namespace.list_children.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["root", "node", "list"])
@pytest.mark.parametrize("failure_type", [StorageFailure, RuntimeError, MissingNode])
async def test_authorization_faults_are_not_mistaken_for_namespace_absence(
    browsing_mocks: BrowsingMocks, operation: str, failure_type: type[Exception],
) -> None:
    context = browsing_mocks
    failure = failure_type("resolver or storage failed")
    context.authorization.require.side_effect = failure
    with pytest.raises(failure_type) as caught:
        await observe(context, operation)
    assert caught.value is failure


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [StorageFailure, RuntimeError, MissingNode])
async def test_child_authorization_fault_aborts_without_returning_partial_results(
    browsing_mocks: BrowsingMocks, failure_type: type[Exception],
) -> None:
    context = browsing_mocks
    first = context.root.model_copy(update={"id": uuid4(), "name": "A"})
    second = context.root.model_copy(update={"id": uuid4(), "name": "B"})
    third = context.root.model_copy(update={"id": uuid4(), "name": "C"})
    context.namespace.list_children.return_value = [first, second, third]
    failure = failure_type("child authorization failed")
    context.authorization.require.side_effect = [None, None, failure]
    with pytest.raises(failure_type) as caught:
        await context.browsing.list_children(caller("alice"), context.root.id)
    assert caught.value is failure
    assert context.authorization.require.await_args_list == [
        call(caller("alice"), node.id, Permission.DISCOVER)
        for node in (context.root, first, second)
    ]


@pytest.mark.asyncio
async def test_child_denial_is_omitted_without_skipping_later_children(
    browsing_mocks: BrowsingMocks,
) -> None:
    context = browsing_mocks
    first = context.root.model_copy(update={"id": uuid4(), "name": "A"})
    hidden = context.root.model_copy(update={"id": uuid4(), "name": "B"})
    last = context.root.model_copy(update={"id": uuid4(), "name": "C"})
    context.namespace.list_children.return_value = [first, hidden, last]
    context.authorization.require.side_effect = [None, None, PermissionDenied("denied"), None]
    result = await context.browsing.list_children(caller("alice"), context.root.id)
    assert [item.id for item in result] == [first.id, last.id]
    assert context.authorization.require.await_count == 4


@pytest.mark.asyncio
async def test_kind_check_happens_after_authorization(
    browsing_mocks: BrowsingMocks,
) -> None:
    context = browsing_mocks

    async def require(observation: CallerSnapshot, node_id: object, permission: Permission) -> None:
        context.namespace.get_node.assert_not_awaited()
        assert observation == caller("alice")
        assert node_id == context.root.id
        assert permission == Permission.DISCOVER

    context.authorization.require.side_effect = require
    assert list(await context.browsing.list_children(caller("alice"), context.root.id)) == []


@pytest.mark.asyncio
async def test_summaries_detach_metadata_even_when_namespace_returns_shared_objects(
    browsing_mocks: BrowsingMocks,
) -> None:
    context = browsing_mocks
    context.root.metadata.attributes["private-attribute"] = "discover-visible"
    context.namespace.list_children.return_value = [context.root, context.root]
    first = await context.browsing.get_root(caller("alice"))
    second = await context.browsing.get_node(caller("alice"), context.root.id)
    listed = await context.browsing.list_children(caller("alice"), context.root.id)
    first.metadata.attributes["private-attribute"] = "changed"
    listed[0].metadata.attributes.clear()
    assert second.metadata.attributes == {"private-attribute": "discover-visible"}
    assert listed[1].metadata.attributes == {"private-attribute": "discover-visible"}
    assert context.root.metadata.attributes == {"private-attribute": "discover-visible"}


@pytest.mark.parametrize("field", [
    "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision"
])
def test_summary_requires_every_explicit_field(field: str) -> None:
    payload = initial_root().model_dump(exclude={"content", field})
    with pytest.raises(ValidationError):
        NodeSummary.model_validate(payload)


@pytest.mark.parametrize("field", ["content", "key", "size"])
def test_summary_rejects_content_or_storage_fields(field: str) -> None:
    payload = initial_root().model_dump(exclude={"content"})
    payload[field] = "forbidden"
    with pytest.raises(ValidationError):
        NodeSummary.model_validate(payload)
