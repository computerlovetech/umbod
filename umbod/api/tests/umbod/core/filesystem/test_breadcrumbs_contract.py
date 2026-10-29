from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import (
    AccessControlDriver, MissingNode, NamespaceDriver, Node, NodeKind, Ownership, PrincipalType,
    RootParent, StorageFailure,
)
from umbod.core.filesystem.authorization import (
    FilesystemAuthorization, FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity,
)
from umbod.core.filesystem.browsing import BreadcrumbItem, Breadcrumbs, BrowsingService
from umbod.core.filesystem.namespace import initial_root
from umbod.core.filesystem.transactions import FilesystemSession
from tests.support.filesystem.authorization import caller, principal


class SuppliedTransactions:
    def __init__(self, session: FilesystemSession) -> None:
        self.session = session
        self.entries = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        self.entries += 1
        yield self.session


@dataclass(frozen=True)
class BreadcrumbMocks:
    service: BrowsingService
    namespace: Mock
    policies: Mock
    resolver: Mock
    transactions: SuppliedTransactions
    root: Node
    target: Node
    outside_namespace: Mock


@pytest.fixture
def context() -> BreadcrumbMocks:
    namespace = create_autospec(NamespaceDriver, instance=True, spec_set=True)
    policies = create_autospec(AccessControlDriver, instance=True, spec_set=True)
    resolver = create_autospec(FilesystemIdentityResolver, instance=True, spec_set=True)
    outside_namespace = create_autospec(NamespaceDriver, instance=True, spec_set=True)
    user = principal("alice", PrincipalType.USER, "issuer")
    resolver.resolve.return_value = ResolvedIdentity(user=user, groups=[])
    root = initial_root()
    target = root.model_copy(update={"id": uuid4(), "parent_id": root.id, "name": "target", "kind": NodeKind.FILE})
    nodes = {root.id: root, target.id: target}
    namespace.get_node.side_effect = nodes.__getitem__
    policies.get_owner.side_effect = lambda node_id: Ownership(node_id=node_id, owner=user)
    transactions = SuppliedTransactions(FilesystemSession(namespace, policies))
    service = BrowsingService(
        outside_namespace, create_autospec(FilesystemAuthorization, instance=True), resolver, transactions,
    )
    return BreadcrumbMocks(service, namespace, policies, resolver, transactions, root, target, outside_namespace)


@pytest.mark.asyncio
async def test_resolves_once_and_reads_only_one_session_without_content_or_other_browsing_reads(context: BreadcrumbMocks) -> None:
    result = await context.service.get_breadcrumbs(caller("alice"), context.target.id)
    assert [item.id for item in result.items] == [context.root.id, context.target.id]
    context.resolver.resolve.assert_awaited_once_with(caller("alice"))
    assert context.transactions.entries == 1
    assert context.outside_namespace.mock_calls == []
    assert {call[0] for call in context.namespace.mock_calls} == {"get_node"}
    assert {call[0] for call in context.policies.mock_calls} == {"get_owner"}


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["cycle", "noncanonical-root", "root-parent", "root-kind", "root-name", "file-ancestor", "identity"])
async def test_corrupt_ancestry_fails_instead_of_returning_partial_or_looping(context: BreadcrumbMocks, corruption: str) -> None:
    root, target = context.root, context.target
    if corruption == "cycle":
        root = root.model_copy(update={"id": uuid4(), "parent_id": target.id, "name": "parent"})
        target = target.model_copy(update={"parent_id": root.id})
    elif corruption == "noncanonical-root":
        target = target.model_copy(update={"parent_id": RootParent()})
    elif corruption == "root-parent":
        root = root.model_copy(update={"parent_id": uuid4()})
    elif corruption == "file-ancestor":
        parent = root.model_copy(update={"id": uuid4(), "parent_id": root.id, "name": "file", "kind": NodeKind.FILE})
        target = target.model_copy(update={"parent_id": parent.id})
        context.namespace.get_node.side_effect = {target.id: target, parent.id: parent, root.id: root}.__getitem__
        with pytest.raises(StorageFailure, match="^Invalid filesystem ancestry$"):
            await context.service.get_breadcrumbs(caller("alice"), context.target.id)
        return
    elif corruption == "root-kind":
        root = root.model_copy(update={"kind": NodeKind.FILE})
    elif corruption == "root-name":
        root = root.model_copy(update={"name": "invented"})
    else:
        target = target.model_copy(update={"id": uuid4()})
    context.namespace.get_node.side_effect = {context.target.id: target, root.id: root}.__getitem__
    with pytest.raises(StorageFailure, match="^Invalid filesystem ancestry$"):
        await context.service.get_breadcrumbs(caller("alice"), context.target.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["target", "ancestor"])
async def test_missing_node_after_successful_authorization_is_storage_failure(context: BreadcrumbMocks, phase: str) -> None:
    context.namespace.get_node.side_effect = (
        [context.target, MissingNode("private")]
        if phase == "target" else [context.target, context.target, context.root, MissingNode("private")]
    )
    with pytest.raises(StorageFailure, match="^Invalid filesystem ancestry$"):
        await context.service.get_breadcrumbs(caller("alice"), context.target.id)


@pytest.mark.asyncio
async def test_missing_ancestor_before_authorization_returns_only_visible_suffix(context: BreadcrumbMocks) -> None:
    context.namespace.get_node.side_effect = [context.target, context.target, MissingNode("private")]
    result = await context.service.get_breadcrumbs(caller("alice"), context.target.id)
    assert result.complete is False
    assert [item.id for item in result.items] == [context.target.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["namespace", "policies", "resolver"])
@pytest.mark.parametrize("failure_type", [StorageFailure, RuntimeError])
async def test_storage_and_resolver_errors_are_not_permission_denial(
    context: BreadcrumbMocks, source: str, failure_type: type[Exception],
) -> None:
    failure = failure_type("private backend failure")
    operations = {"namespace": context.namespace.get_node, "policies": context.policies.get_owner, "resolver": context.resolver.resolve}
    operations[source].side_effect = failure
    with pytest.raises(failure_type) as caught:
        await context.service.get_breadcrumbs(caller("alice"), context.target.id)
    assert caught.value is failure
    assert not isinstance(caught.value, PermissionDenied)


@pytest.mark.asyncio
async def test_resolver_missing_node_is_not_mistaken_for_namespace_absence(context: BreadcrumbMocks) -> None:
    failure = MissingNode("resolver failure")
    context.resolver.resolve.side_effect = failure
    with pytest.raises(MissingNode) as caught:
        await context.service.get_breadcrumbs(caller("alice"), context.target.id)
    assert caught.value is failure


@pytest.mark.asyncio
async def test_deep_valid_ancestry_has_no_silent_depth_limit(context: BreadcrumbMocks) -> None:
    nodes = [context.root]
    for index in range(1100):
        nodes.append(context.root.model_copy(update={"id": uuid4(), "parent_id": nodes[-1].id, "name": str(index)}))
    context.namespace.get_node.side_effect = {node.id: node for node in nodes}.__getitem__
    result = await context.service.get_breadcrumbs(caller("alice"), nodes[-1].id)
    assert result.complete is True
    assert [item.id for item in result.items] == [node.id for node in nodes]


def test_models_require_nonempty_explicit_minimal_fields() -> None:
    with pytest.raises(ValidationError):
        Breadcrumbs(items=[], complete=False)
    for field in ("id", "name", "kind"):
        with pytest.raises(ValidationError):
            BreadcrumbItem.model_validate({key: value for key, value in {"id": uuid4(), "name": "", "kind": "directory"}.items() if key != field})
    for field in ("metadata", "parent_id", "reason", "count"):
        with pytest.raises(ValidationError):
            BreadcrumbItem.model_validate({"id": uuid4(), "name": "", "kind": "directory", field: "private"})

