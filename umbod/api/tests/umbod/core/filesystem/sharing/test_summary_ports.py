from asyncio import CancelledError
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import AccessGrant, NodeId, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import (
    PermissionDenied, ResolvedIdentity, UnresolvedIdentity, VerifiedIdentityResolver,
)
from umbod.core.filesystem.namespace import initial_root
from umbod.core.filesystem.sharing import FilesystemSharing, SharingService
from umbod.core.filesystem.sharing.ports import SharingSession
from umbod.core.groups.models import Group
from tests.support.filesystem.group_sharing import InMemorySharingTransactions, SharingGroups
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .test_ports import transactions


class CountingResolver(VerifiedIdentityResolver):
    def __init__(self) -> None:
        self.reads = 0

    async def resolve(self, snapshot: CallerSnapshot) -> ResolvedIdentity | UnresolvedIdentity:
        self.reads += 1
        return await super().resolve(snapshot)


class CountingGroups(SharingGroups):
    def __init__(self) -> None:
        super().__init__(frozenset({"team"}))
        self.ids_reads = 0

    async def registered_group_ids(self) -> frozenset[str]:
        self.ids_reads += 1
        return await super().registered_group_ids()


class CountingTransactions(InMemorySharingTransactions):
    def __init__(self) -> None:
        ports = transactions()
        super().__init__(ports.namespace, ports.policies, CountingGroups())
        self.entries = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SharingSession]:
        self.entries += 1
        async with super().transaction() as session:
            yield session


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [True, False])
async def test_batch_resolves_once_and_reads_catalogue_only_once_if_authorized(authorized: bool) -> None:
    ports = CountingTransactions()
    resolver = CountingResolver()
    service: FilesystemSharing = SharingService(resolver, ports, "issuer")
    root = initial_root()
    second = root.model_copy(update={"id": uuid4()})
    ports.namespace.nodes[second.id] = second
    ports.policies.owners[second.id] = ports.policies.owners[root.id].model_copy(update={"node_id": second.id})
    actor = caller() if authorized else snapshot("bob", "issuer", ())
    result = await service.summarize_nodes(actor, (second.id, root.id, second.id, root.id))
    assert [node.node_id for node in result.nodes] == [second.id, root.id]
    assert [node.can_share for node in result.nodes] == [authorized, authorized]
    assert resolver.reads == ports.entries == 1
    assert ports.groups.reads == int(authorized)
    assert isinstance(ports.groups, CountingGroups)
    assert ports.groups.ids_reads == 0


@pytest.mark.asyncio
async def test_empty_batch_validates_identity_without_transaction() -> None:
    ports = CountingTransactions()
    resolver = CountingResolver()
    service: FilesystemSharing = SharingService(resolver, ports, "issuer")
    assert (await service.summarize_nodes(caller(), ())).nodes == ()
    assert resolver.reads == 1
    assert ports.entries == ports.groups.reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [True, False])
async def test_unresolved_caller_is_denied_before_transaction(empty: bool) -> None:
    ports = CountingTransactions()
    service: FilesystemSharing = SharingService(CountingResolver(), ports, "issuer")
    with pytest.raises(PermissionDenied):
        await service.summarize_nodes(snapshot("alice", "issuer", ("",)), () if empty else (initial_root().id,))
    assert ports.entries == ports.groups.reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("storage failure"), CancelledError()])
@pytest.mark.parametrize("stage", ["namespace", "catalogue"])
async def test_storage_errors_and_cancellation_propagate(failure: BaseException, stage: str, monkeypatch: pytest.MonkeyPatch) -> None:
    ports = CountingTransactions()
    service: FilesystemSharing = SharingService(CountingResolver(), ports, "issuer")

    async def fail_node(node_id: NodeId) -> None:
        raise failure

    async def fail_groups() -> tuple[Group, ...]:
        raise failure

    if stage == "namespace":
        monkeypatch.setattr(ports.namespace, "get_node", fail_node)
    else:
        monkeypatch.setattr(ports.groups, "registered_groups", fail_groups)
    with pytest.raises(type(failure)) as caught:
        await service.summarize_nodes(caller(), (initial_root().id,))
    assert caught.value is failure


@pytest.mark.asyncio
async def test_protected_same_principal_collision_does_not_leak_manageable_grant() -> None:
    ports = CountingTransactions()
    root = initial_root()
    principal = Principal(type=PrincipalType.GROUP, issuer="issuer", id="team")
    editable = AccessGrant(node_id=root.id, principal=principal, permissions={Permission.READ}, recursive=False)
    protected = editable.model_copy(update={"recursive": True})

    async def grants(node_id: NodeId) -> list[AccessGrant]:
        return [editable, protected]

    ports.policies.list_grants = grants
    service: FilesystemSharing = SharingService(CountingResolver(), ports, "issuer")
    assert (await service.inspect(caller(), root.id)).groups == ()
    summary = (await service.summarize_nodes(caller(), (root.id,))).nodes[0]
    assert summary.model_dump(mode="json") == {"node_id": str(root.id), "can_share": True, "grants": []}
