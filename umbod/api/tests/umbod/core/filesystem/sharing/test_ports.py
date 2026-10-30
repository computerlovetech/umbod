from uuid import uuid4

import pytest

from umbod.core.filesystem import AccessGrant, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import initial_root
from umbod.core.filesystem.sharing import GroupPolicy, ReplaceNodeGroupPolicy, SharingService
from tests.support.filesystem.group_sharing import (
    InMemorySharingTransactions, SharingGroups, SharingNamespace, SharingPolicies,
)
from tests.umbod.core.filesystem.test_authorized_content import alice, caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot


def transactions() -> InMemorySharingTransactions:
    root = initial_root()
    return InMemorySharingTransactions(
        SharingNamespace((root,)),
        SharingPolicies(Ownership(node_id=root.id, owner=alice()), ()),
        SharingGroups(frozenset({"team"})),
    )


@pytest.mark.asyncio
async def test_denied_or_missing_nodes_never_read_recipient_catalogue() -> None:
    ports = transactions()
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    for node_id in (initial_root().id, uuid4()):
        with pytest.raises(PermissionDenied):
            await service.replace(snapshot("admin", "issuer", ("admins",)), node_id, ReplaceNodeGroupPolicy(expected_revision="unknown", groups=()))
        with pytest.raises(PermissionDenied):
            await service.eligible_groups(snapshot("admin", "issuer", ("admins",)), node_id)
    assert ports.groups.reads == 0


@pytest.mark.asyncio
async def test_port_fake_replacement_returns_authoritative_policy() -> None:
    ports = transactions()
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    root = initial_root()
    before = await service.inspect(caller(), root.id)
    policy = GroupPolicy(group_id="team", permissions=frozenset({Permission.READ}))
    result = await service.replace(caller(), root.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=(policy,)))
    assert result.groups == (policy,)
    assert result.revision != before.revision
    assert await service.inspect(caller(), root.id) == result
    assert tuple(group.group_id for group in (await service.eligible_groups(caller(), root.id)).groups) == ("team",)


@pytest.mark.asyncio
async def test_grant_order_does_not_change_canonical_revision() -> None:
    ports = transactions()
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    root = initial_root()
    grants = tuple(
        AccessGrant(node_id=root.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id=identifier), permissions=set(Permission), recursive=False)
        for identifier in ("bob", "charlie")
    )
    for grant in grants:
        await ports.policies.upsert(grant)
    before = await service.inspect(caller(), root.id)
    for grant in grants:
        await ports.policies.remove_grant(root.id, grant.principal)
    for grant in reversed(grants):
        await ports.policies.upsert(grant)
    assert await service.inspect(caller(), root.id) == before
