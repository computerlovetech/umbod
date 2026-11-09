from tests.support.filesystem.sharing_policy import GROUP_SCOPE, group_commands, group_policies, blocked_groups
from dataclasses import replace as replace_context
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import (
    AccessGrant, ContentRef, NodeKind, Ownership, Permission, Principal, PrincipalType,
    RevisionConflict, SYSTEM_ROOT_OWNER,
)
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.group_policy import GroupPolicy as NeutralGroupPolicy
from umbod.core.filesystem.administration import GroupPolicy as RootGroupPolicy
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.sharing import (
    GroupPolicy, InvalidSharingPolicy, ReplaceNodePolicy, SharingPolicyUnavailable,
)
from umbod.core.filesystem.stores.access_control import SessionAccessControl
from umbod.core.groups import RegisterGroup, UpdateGroupMetadata
from umbod.core.persistence import TransactionMode
from umbod.infrastructure import create_filesystem_sharing
from tests.umbod.core.filesystem.test_authorized_content import alice, caller, metadata
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import SharingContext


def group(identifier: str) -> GroupPolicy:
    return GroupPolicy(group_id=identifier, permissions=frozenset({Permission.READ, Permission.DISCOVER}))


def principal(identifier: str) -> Principal:
    return Principal(type=PrincipalType.GROUP, issuer="issuer", id=identifier)


async def replace(context: SharingContext, groups: tuple[GroupPolicy, ...]) -> None:
    view = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=view.revision, grants=group_commands(groups)))


@pytest.mark.asyncio
async def test_owner_replaces_exact_registered_groups_without_changing_node_or_owner(context: SharingContext) -> None:
    identifiers = (" Team ", "Team", "team", "a/b")
    for identifier in identifiers:
        await context.groups.register_group(RegisterGroup(group_id=identifier))
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    result = await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group",
        expected_revision=before.revision, grants=group_commands(tuple(group(value) for value in identifiers)),
    ))
    assert group_policies(result) == tuple(group(value) for value in sorted(identifiers))
    assert result.revision != before.revision
    assert await context.service.inspect(caller(), context.node.id, GROUP_SCOPE) == result
    assert await context.namespace.get_node(context.node.id) == context.node
    assert (await context.policies.get_owner(context.node.id)).owner == alice()
    await replace(context, ())
    assert await context.policies.list_grants(context.node.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.SHARE}, {Permission.READ, Permission.WRITE}])
async def test_both_permissions_required_before_revision_or_recipient_validation(context: SharingContext, permissions: set[Permission]) -> None:
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=principal("admins"), permissions=permissions, recursive=False))
    for node_id in (context.node.id, uuid4()):
        actor = snapshot("admin", "issuer", ("admins",))
        with pytest.raises(PermissionDenied):
            await context.service.inspect(actor, node_id, GROUP_SCOPE)
        with pytest.raises(PermissionDenied):
            await context.service.replace(actor, node_id, ReplaceNodePolicy(recipient_type="group", expected_revision="stale", grants=group_commands((group("unknown"),))))


@pytest.mark.asyncio
@pytest.mark.parametrize("group_authority", [False, True])
async def test_direct_user_or_group_authority_allows_sharing_without_parent_access(context: SharingContext, group_authority: bool) -> None:
    target = principal("sharers") if group_authority else Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    actor = snapshot("bob", "issuer", ("sharers",) if group_authority else ())
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=target, permissions={Permission.SHARE, Permission.DISCOVER}, recursive=False))
    view = await context.service.inspect(actor, context.node.id, GROUP_SCOPE)
    result = await context.service.replace(actor, context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=view.revision, grants=group_commands(())))
    assert group_policies(result) == ()
    if group_authority:
        with pytest.raises(PermissionDenied):
            await context.service.inspect(actor, context.node.id, GROUP_SCOPE)


@pytest.mark.asyncio
async def test_unregistered_recipient_rejects_entire_replacement_without_mutation(context: SharingContext) -> None:
    await context.groups.register_group(RegisterGroup(group_id="old"))
    await context.groups.register_group(RegisterGroup(group_id="valid"))
    await replace(context, (group("old"),))
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    with pytest.raises(InvalidSharingPolicy):
        await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=before.revision, grants=group_commands((group("valid"), group("unregistered")))))
    assert await context.service.inspect(caller(), context.node.id, GROUP_SCOPE) == before
    assert {item.group_id for item in await context.groups.list_groups()} == {"old", "valid"}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["grant", "owner", "node", "issuer"])
async def test_any_policy_snapshot_change_invalidates_revision(context: SharingContext, change: str) -> None:
    if change == "node":
        node = await context.namespace.create_node(context.node.id, "file", NodeKind.FILE, metadata())
        await context.policies.set_owner(Ownership(node_id=node.id, owner=alice()))
        context = replace_context(context, node=node)
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    service = context.service
    if change == "grant":
        await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=SYSTEM_ROOT_OWNER, permissions={Permission.READ}, recursive=True))
    elif change == "owner":
        await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=alice(), permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False))
        before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
        await context.policies.set_owner(Ownership(node_id=context.node.id, owner=SYSTEM_ROOT_OWNER))
    elif change == "node":
        await context.namespace.update_node(context.node.id, content=ContentRef(key="content", size=1), expected_revision=context.node.revision)
    else:
        service = create_filesystem_sharing(database=context.database, resolver=VerifiedIdentityResolver(), issuer="other")
    with pytest.raises(RevisionConflict):
        await service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=before.revision, grants=group_commands(())))


@pytest.mark.asyncio
async def test_protected_grants_are_preserved_and_same_principal_collisions_rejected(context: SharingContext) -> None:
    orphan = AccessGrant(node_id=context.node.id, principal=principal("orphan"), permissions={Permission.READ}, recursive=False)
    async with context.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await SessionAccessControl(session).upsert_registered_grant(orphan)
    protected = [orphan]
    for target, permissions, recursive in (
        (alice(), {Permission.READ}, False),
        (SYSTEM_ROOT_OWNER, {Permission.SHARE}, False),
        (Principal(type=PrincipalType.GROUP, issuer="foreign", id="foreign"), {Permission.READ}, False),
        (principal("recursive"), set(), True),
        (principal("empty"), set(), False),
        (principal("  "), set(), False),
    ):
        grant = AccessGrant(node_id=context.node.id, principal=target, permissions=permissions, recursive=recursive)
        await context.policies.add_grant(grant)
        protected.append(grant)
    await context.groups.register_group(RegisterGroup(group_id="editable"))
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    assert group_policies(before) == ()
    assert blocked_groups(before) == ("empty", "orphan", "recursive")
    for identifier in blocked_groups(before):
        with pytest.raises(InvalidSharingPolicy):
            await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=before.revision, grants=group_commands((group(identifier),))))
        assert await context.service.inspect(caller(), context.node.id, GROUP_SCOPE) == before
    await replace(context, (group("editable"),))
    await replace(context, ())
    assert {grant.principal: grant for grant in await context.policies.list_grants(context.node.id)} == {grant.principal: grant for grant in protected}


@pytest.mark.asyncio
async def test_registering_orphan_changes_revision_but_unrelated_group_metadata_does_not(context: SharingContext) -> None:
    async with context.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await SessionAccessControl(session).upsert_registered_grant(AccessGrant(node_id=context.node.id, principal=principal("orphan"), permissions={Permission.READ}, recursive=False))
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    await context.groups.register_group(RegisterGroup(group_id="unrelated"))
    assert await context.service.inspect(caller(), context.node.id, GROUP_SCOPE) == before
    await context.groups.register_group(RegisterGroup(group_id="orphan"))
    after = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    assert after.revision != before.revision
    assert blocked_groups(after) == ()
    with pytest.raises(RevisionConflict):
        await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=before.revision, grants=group_commands(())))
    await context.groups.update_group_metadata("orphan", UpdateGroupMetadata(expected_revision=1, label="New label", description="description"))
    renamed = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    assert renamed.revision == after.revision
    assert group_policies(renamed) == group_policies(after)
    assert renamed.grants[0].recipient.label == "New label"


@pytest.mark.asyncio
async def test_direct_only_directory_grants_do_not_inherit_and_file_access_needs_no_ancestor_access(context: SharingContext) -> None:
    child = await context.namespace.create_node(context.node.id, "child", NodeKind.FILE, metadata())
    await context.policies.set_owner(Ownership(node_id=child.id, owner=alice()))
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=principal("team"), permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False))
    actor = snapshot("bob", "issuer", ("team",))
    with pytest.raises(PermissionDenied):
        await context.service.inspect(actor, child.id, GROUP_SCOPE)
    await context.policies.remove_grant(context.node.id, principal("team"))
    await context.policies.add_grant(AccessGrant(node_id=child.id, principal=principal("team"), permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False))
    assert (await context.service.inspect(actor, child.id, GROUP_SCOPE)).node_id == child.id
    for node_id in (context.node.id, ROOT_ID):
        with pytest.raises(PermissionDenied):
            await context.service.inspect(actor, node_id, GROUP_SCOPE)


@pytest.mark.parametrize("issuer", ["", " \t"])
def test_blank_configured_issuer_fails_closed(context: SharingContext, issuer: str) -> None:
    with pytest.raises(SharingPolicyUnavailable):
        create_filesystem_sharing(database=context.database, resolver=VerifiedIdentityResolver(), issuer=issuer)


def test_strict_policy_models_reuse_frozen_group_validation() -> None:
    assert GroupPolicy is RootGroupPolicy is NeutralGroupPolicy
    policy = group(" Team ")
    assert policy.group_id == " Team "
    for payload in (
        {"recipient_type": "group", "expected_revision": "r", "grants": group_commands((policy, policy))},
        {"recipient_type": "group", "expected_revision": "r", "grants": (), "issuer": "other"},
        {"recipient_type": "group", "grants": ()},
    ):
        with pytest.raises(ValidationError):
            ReplaceNodePolicy.model_validate(payload)
    with pytest.raises(ValidationError):
        policy.group_id = "changed"
