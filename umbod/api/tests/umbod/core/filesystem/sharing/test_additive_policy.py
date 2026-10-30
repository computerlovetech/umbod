from dataclasses import replace
from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    AccessGrant, NodeKind, Ownership, Permission, Principal, PrincipalType,
    RevisionConflict, SYSTEM_ROOT_OWNER,
)
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.sharing import GroupPolicy, InvalidSharingPolicy, ReplaceNodeGroupPolicy
from umbod.core.filesystem.stores.access_control import SessionAccessControl
from umbod.core.groups import RegisterGroup
from umbod.core.persistence import TransactionMode
from tests.umbod.core.filesystem.test_authorized_content import alice, caller, metadata
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import SharingContext
from .test_policy import principal


def command(identifier: str, *permissions: Permission) -> GroupPolicy:
    return GroupPolicy(group_id=identifier, permissions=frozenset(permissions))


@pytest.mark.asyncio
async def test_additive_sharing_preserves_exact_recipient_ids_and_unions_permissions(context: SharingContext) -> None:
    identifiers = (" Team ", "Team", "team", "a/b")
    for identifier in identifiers:
        await context.groups.register_group(RegisterGroup(group_id=identifier))
        first = await context.service.share(caller(), context.node.id, command(identifier, Permission.READ))
        assert first.changed
        added = await context.service.share(caller(), context.node.id, command(identifier, Permission.WRITE))
        assert added.changed
        assert added.permissions == frozenset({Permission.READ, Permission.WRITE})
        repeated = await context.service.share(caller(), context.node.id, command(identifier, Permission.READ))
        assert not repeated.changed
        assert repeated.permissions == added.permissions
    assert (await context.service.inspect(caller(), context.node.id)).groups == tuple(
        command(identifier, Permission.READ, Permission.WRITE) for identifier in sorted(identifiers)
    )
    assert await context.namespace.get_node(context.node.id) == context.node
    assert (await context.policies.get_owner(context.node.id)).owner == alice()


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.SHARE}, {Permission.READ, Permission.WRITE}])
async def test_share_denies_missing_or_incomplete_direct_authority(context: SharingContext, permissions: set[Permission]) -> None:
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=principal("admins"), permissions=permissions, recursive=False))
    actor = snapshot("admin", "issuer", ("admins",))
    for node_id in (context.node.id, uuid4()):
        with pytest.raises(PermissionDenied):
            await context.service.share(actor, node_id, command("unknown", Permission.READ))


@pytest.mark.asyncio
@pytest.mark.parametrize("group_authority", [False, True])
async def test_direct_delegate_can_share_without_ancestor_access(context: SharingContext, group_authority: bool) -> None:
    await context.groups.register_group(RegisterGroup(group_id="recipient"))
    target = principal("delegates") if group_authority else Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=target, permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False))
    actor = snapshot("bob", "issuer", ("delegates",) if group_authority else ())
    assert (await context.service.share(actor, context.node.id, command("recipient", Permission.READ))).changed
    await context.policies.remove_grant(context.node.id, target)
    with pytest.raises(PermissionDenied):
        await context.service.share(actor, context.node.id, command("recipient", Permission.READ))


@pytest.mark.asyncio
async def test_ancestor_authority_does_not_allow_sharing_child(context: SharingContext) -> None:
    child = await context.namespace.create_node(context.node.id, "child", NodeKind.FILE, metadata())
    await context.policies.set_owner(Ownership(node_id=child.id, owner=alice()))
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=principal("delegates"), permissions={Permission.DISCOVER, Permission.SHARE}, recursive=True))
    with pytest.raises(PermissionDenied):
        await context.service.share(snapshot("bob", "issuer", ("delegates",)), child.id, command("unknown", Permission.READ))


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["team", " Team", "Team ", " Team "])
async def test_recipient_matching_does_not_trim_or_fold_case(context: SharingContext, identifier: str) -> None:
    await context.groups.register_group(RegisterGroup(group_id="Team"))
    before = await context.service.inspect(caller(), context.node.id)
    with pytest.raises(InvalidSharingPolicy):
        await context.service.share(caller(), context.node.id, command(identifier, Permission.READ))
    assert await context.service.inspect(caller(), context.node.id) == before
    assert tuple(group.group_id for group in await context.groups.list_groups()) == ("Team",)


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", [False, True])
async def test_unknown_or_deleted_recipient_is_not_registered_or_granted(context: SharingContext, deleted: bool) -> None:
    if deleted:
        await context.groups.register_group(RegisterGroup(group_id="team"))
        await context.groups.delete_group("team")
    before = await context.service.inspect(caller(), context.node.id)
    with pytest.raises(InvalidSharingPolicy):
        await context.service.share(caller(), context.node.id, command("team", Permission.READ))
    assert await context.service.inspect(caller(), context.node.id) == before
    assert await context.groups.list_groups() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive,permissions", [(True, {Permission.READ}), (False, set())])
async def test_protected_recipient_collision_is_not_overwritten(context: SharingContext, recursive: bool, permissions: set[Permission]) -> None:
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=principal("team"), permissions=permissions, recursive=recursive))
    before = await context.service.inspect(caller(), context.node.id)
    groups = await context.groups.list_groups()
    with pytest.raises(InvalidSharingPolicy):
        await context.service.share(caller(), context.node.id, command("team", Permission.WRITE))
    assert await context.service.inspect(caller(), context.node.id) == before
    assert await context.groups.list_groups() == groups


@pytest.mark.asyncio
async def test_additive_share_preserves_unrelated_protected_policy_owner_and_content(context: SharingContext) -> None:
    node = await context.namespace.create_node(context.node.id, "file", NodeKind.FILE, metadata())
    await context.policies.set_owner(Ownership(node_id=node.id, owner=alice()))
    context = replace(context, node=node)
    for identifier in ("recipient", "unrelated"):
        await context.groups.register_group(RegisterGroup(group_id=identifier))
    protected = [
        AccessGrant(node_id=node.id, principal=target, permissions=permissions, recursive=recursive)
        for target, permissions, recursive in (
            (alice(), {Permission.READ}, False),
            (SYSTEM_ROOT_OWNER, {Permission.SHARE}, False),
            (Principal(type=PrincipalType.GROUP, issuer="foreign", id="recipient"), {Permission.WRITE}, False),
            (principal("recursive"), {Permission.READ}, True),
            (principal("empty"), set(), False),
            (principal("unrelated"), {Permission.DISCOVER}, False),
        )
    ]
    for grant in protected:
        await context.policies.add_grant(grant)
    orphan = AccessGrant(node_id=node.id, principal=principal("orphan"), permissions={Permission.READ}, recursive=False)
    async with context.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await SessionAccessControl(session).upsert_registered_grant(orphan)
    protected.append(orphan)
    before_groups = await context.groups.list_groups()
    ownership = await context.policies.get_owner(node.id)
    await context.service.share(caller(), node.id, command("recipient", Permission.READ))
    grants = {grant.principal: grant for grant in await context.policies.list_grants(node.id)}
    assert {grant.principal: grants[grant.principal] for grant in protected} == {grant.principal: grant for grant in protected}
    assert grants[principal("recipient")].permissions == {Permission.READ}
    assert not grants[principal("recipient")].recursive
    assert await context.groups.list_groups() == before_groups
    assert await context.policies.get_owner(node.id) == ownership
    assert await context.namespace.get_node(node.id) == node
    with pytest.raises(InvalidSharingPolicy):
        await context.service.share(caller(), node.id, command("orphan", Permission.READ))


@pytest.mark.asyncio
async def test_share_invalidates_previous_replacement_but_allows_explicit_fresh_replace(context: SharingContext) -> None:
    await context.groups.register_group(RegisterGroup(group_id="team"))
    before = await context.service.inspect(caller(), context.node.id)
    await context.service.share(caller(), context.node.id, command("team", Permission.READ))
    with pytest.raises(RevisionConflict):
        await context.service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=()))
    current = await context.service.inspect(caller(), context.node.id)
    await context.service.share(caller(), context.node.id, command("team", Permission.READ))
    assert await context.service.inspect(caller(), context.node.id) == current
    result = await context.service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=current.revision, groups=()))
    assert result.groups == ()
