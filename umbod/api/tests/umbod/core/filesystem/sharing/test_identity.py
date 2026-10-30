import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.sharing import GroupPolicy, ReplaceNodeGroupPolicy
from umbod.core.groups import RegisterGroup
from umbod.infrastructure import create_filesystem_sharing
from tests.umbod.core.filesystem.test_authorized_content import caller, metadata
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import SharingContext


@pytest.mark.asyncio
async def test_group_ownership_is_direct_authority(context: SharingContext) -> None:
    owner = Principal(type=PrincipalType.GROUP, issuer="issuer", id="owners")
    await context.policies.set_owner(Ownership(node_id=context.node.id, owner=owner))
    actor = snapshot("bob", "issuer", ("owners",))
    before = await context.service.inspect(actor, context.node.id)
    result = await context.service.replace(actor, context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=()))
    assert result == before
    assert (await context.policies.get_owner(context.node.id)).owner == owner


@pytest.mark.asyncio
async def test_unowned_nodes_and_unresolved_identity_fail_closed(context: SharingContext) -> None:
    unowned = await context.namespace.create_node(context.node.id, "unowned", NodeKind.FILE, metadata())
    await context.policies.add_grant(AccessGrant(
        node_id=unowned.id,
        principal=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"),
        permissions=set(Permission), recursive=False,
    ))
    with pytest.raises(PermissionDenied):
        await context.service.inspect(caller(), unowned.id)
    unresolved = snapshot("alice", "issuer", ("",))
    with pytest.raises(PermissionDenied):
        await context.service.replace(unresolved, context.node.id, ReplaceNodeGroupPolicy(expected_revision="unknown", groups=()))


@pytest.mark.asyncio
async def test_configured_issuer_is_exact_and_independent_of_caller_issuer(context: SharingContext) -> None:
    await context.groups.register_group(RegisterGroup(group_id=" Team "))
    service = create_filesystem_sharing(database=context.database, resolver=VerifiedIdentityResolver(), issuer=" Exact Issuer ")
    policy = GroupPolicy(group_id=" Team ", permissions=frozenset({Permission.SHARE, Permission.DISCOVER}))
    before = await service.inspect(caller(), context.node.id)
    saved = await service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=(policy,)))
    grants = await context.policies.list_grants(context.node.id)
    assert grants[0].principal == Principal(type=PrincipalType.GROUP, issuer=" Exact Issuer ", id=" Team ")
    exact = snapshot("bob", " Exact Issuer ", (" Team ",))
    assert await service.inspect(exact, context.node.id) == saved
    for actor in (snapshot("bob", "Exact Issuer", (" Team ",)), snapshot("bob", " Exact Issuer ", ("Team",))):
        with pytest.raises(PermissionDenied):
            await service.inspect(actor, context.node.id)
    view = await context.service.inspect(caller(), context.node.id)
    assert view.groups == ()
    assert view.revision != saved.revision
