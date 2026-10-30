from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    AccessGrant, NodeKind, Ownership, Permission, Principal, PrincipalType, SYSTEM_ROOT_OWNER,
)
from umbod.core.filesystem.sharing import RestrictedNodeSharingSummary, ShareableNodeSharingSummary
from umbod.core.filesystem.stores.access_control import SessionAccessControl
from umbod.core.groups import RegisterGroup, UpdateGroupMetadata
from umbod.core.persistence import TransactionMode
from tests.umbod.core.filesystem.test_authorized_content import alice, caller, metadata
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import SharingContext


@pytest.mark.asyncio
async def test_batch_summaries_classify_mixed_direct_authority_without_leaking_grants(context: SharingContext) -> None:
    identifiers = [context.node.id]
    for index, permissions in enumerate((set(), {Permission.DISCOVER}, {Permission.SHARE}, {Permission.DISCOVER, Permission.SHARE})):
        node = await context.namespace.create_node(context.node.id, str(index), NodeKind.FILE, metadata())
        await context.policies.set_owner(Ownership(node_id=node.id, owner=SYSTEM_ROOT_OWNER))
        await context.policies.add_grant(AccessGrant(node_id=node.id, principal=alice(), permissions=permissions, recursive=False))
        identifiers.append(node.id)
    unowned = await context.namespace.create_node(context.node.id, "unowned", NodeKind.FILE, metadata())
    await context.policies.add_grant(AccessGrant(node_id=unowned.id, principal=alice(), permissions=set(Permission), recursive=False))
    deleted = await context.namespace.create_node(context.node.id, "deleted", NodeKind.FILE, metadata())
    await context.policies.set_owner(Ownership(node_id=deleted.id, owner=alice()))
    await context.namespace.delete_node(deleted.id, expected_revision=deleted.revision)
    identifiers.extend((unowned.id, deleted.id, uuid4()))
    result = await context.service.summarize_nodes(caller(), tuple(identifiers))
    assert [node.can_share for node in result.nodes] == [True, False, False, False, True, False, False, False]
    for node in result.nodes:
        if isinstance(node, RestrictedNodeSharingSummary):
            assert "grants" not in node.model_dump(mode="json")
        else:
            assert node.grants == ()


@pytest.mark.asyncio
async def test_summary_matches_inspect_protected_scope_and_current_exact_labels(context: SharingContext) -> None:
    identifiers = (" Team ", "Team", "team", "a/b", "recursive", "empty")
    for identifier in identifiers:
        await context.groups.register_group(RegisterGroup(group_id=identifier))
    for identifier in identifiers:
        await context.policies.add_grant(AccessGrant(
            node_id=context.node.id,
            principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id=identifier),
            permissions=set() if identifier == "empty" else {Permission.READ, Permission.DISCOVER},
            recursive=identifier == "recursive",
        ))
    for target in (alice(), SYSTEM_ROOT_OWNER, Principal(type=PrincipalType.GROUP, issuer="foreign", id="Team"), Principal(type=PrincipalType.GROUP, issuer="issuer", id="  ")):
        await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=target, permissions={Permission.READ}, recursive=False))
    async with context.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await SessionAccessControl(session).upsert_registered_grant(AccessGrant(
            node_id=context.node.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="orphan"),
            permissions={Permission.READ}, recursive=False,
        ))
    await context.groups.update_group_metadata(" Team ", UpdateGroupMetadata(expected_revision=1, label="Current label", description="hidden description"))
    view = await context.service.inspect(caller(), context.node.id)
    summary = (await context.service.summarize_nodes(caller(), (context.node.id,))).nodes[0]
    assert isinstance(summary, ShareableNodeSharingSummary)
    assert [(grant.recipient.group_id, grant.permissions) for grant in summary.grants] == [(grant.group_id, grant.permissions) for grant in view.groups]
    assert [grant.recipient.group_id for grant in summary.grants] == [" Team ", "Team", "a/b", "team"]
    assert summary.grants[0].recipient.label == "Current label"
    assert set(summary.model_dump()) == {"node_id", "can_share", "grants"}
    assert all(set(grant.recipient.model_dump()) == {"type", "group_id", "label"} for grant in summary.grants)


@pytest.mark.asyncio
async def test_summary_grants_and_authority_do_not_inherit(context: SharingContext) -> None:
    child = await context.namespace.create_node(context.node.id, "child", NodeKind.FILE, metadata())
    await context.policies.set_owner(Ownership(node_id=child.id, owner=alice()))
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="team"),
        permissions={Permission.DISCOVER, Permission.SHARE}, recursive=True,
    ))
    result = await context.service.summarize_nodes(snapshot("bob", "issuer", ("team",)), (context.node.id, child.id))
    assert [node.can_share for node in result.nodes] == [True, False]
    assert isinstance(result.nodes[0], ShareableNodeSharingSummary)
    assert result.nodes[0].grants == ()
