import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, Ownership, Permission
from umbod.core.filesystem.sharing import ReplaceNodePolicy, ShareNodePolicy
from umbod.core.groups import RegisterGroup
from tests.support.filesystem.sharing_policy import GROUP_SCOPE
from tests.umbod.core.filesystem.test_authorized_content import alice, caller, metadata
from .conftest import SharingContext
from .test_additive_policy import command
from .test_policy import principal


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,requested,expected", [
    (NodeKind.DIRECTORY, True, True), (NodeKind.DIRECTORY, False, False),
    (NodeKind.FILE, True, False), (NodeKind.FILE, False, False),
])
async def test_scope_is_normalized_and_returned_from_policy_and_summary(
    context: SharingContext, kind: NodeKind, requested: bool, expected: bool,
) -> None:
    await context.groups.register_group(RegisterGroup(group_id="team"))
    node = await context.namespace.create_node(context.node.id, "target", kind, metadata())
    await context.policies.set_owner(Ownership(node_id=node.id, owner=alice()))
    policy = command("team", Permission.READ).model_copy(update={"recursive": requested})
    first = await context.service.share(caller(), node.id, policy)
    assert first.changed and first.recursive is expected
    assert not (await context.service.share(caller(), node.id, policy)).changed
    view = await context.service.inspect(caller(), node.id, GROUP_SCOPE)
    summary = (await context.service.summarize_nodes(caller(), (node.id,))).nodes[0]
    assert summary.can_share and summary.grants == view.grants
    assert view.grants[0].recursive is expected
    assert (await context.policies.list_grants(node.id))[0].recursive is expected


@pytest.mark.asyncio
async def test_default_folder_share_is_recursive_and_does_not_copy_grants(context: SharingContext) -> None:
    await context.groups.register_group(RegisterGroup(group_id="team"))
    child = await context.namespace.create_node(context.node.id, "child", NodeKind.FILE, metadata())
    result = await context.service.share(caller(), context.node.id, command("team", Permission.READ))
    assert result.recursive is True
    assert await context.policies.list_grants(child.id) == []


@pytest.mark.asyncio
async def test_scope_only_addition_changes_revision_and_cannot_shrink_scope(context: SharingContext) -> None:
    await context.groups.register_group(RegisterGroup(group_id="team"))
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=principal("team"), permissions={Permission.READ}, recursive=False,
    ))
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    omitted = command("team", Permission.READ)
    repeated_legacy = await context.service.share(caller(), context.node.id, omitted)
    assert not repeated_legacy.changed and not repeated_legacy.recursive
    assert (await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)) == before
    policy = omitted.model_copy(update={"recursive": True})
    widened = await context.service.share(caller(), context.node.id, policy)
    assert widened.changed and widened.recursive
    current = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    assert current.revision != before.revision
    repeated = await context.service.share(caller(), context.node.id, policy.model_copy(update={"recursive": False}))
    assert not repeated.changed and repeated.recursive
    assert (await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)).revision == current.revision


@pytest.mark.asyncio
async def test_replacement_roundtrips_legacy_scope_and_can_explicitly_widen_or_narrow(context: SharingContext) -> None:
    for identifier in ("legacy", "other"):
        await context.groups.register_group(RegisterGroup(group_id=identifier))
        await context.policies.add_grant(AccessGrant(
            node_id=context.node.id, principal=principal(identifier), permissions={Permission.READ}, recursive=False,
        ))
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    policies = tuple(ShareNodePolicy(
        recipient={key: value for key, value in grant.recipient.model_dump().items() if key != "label"},
        permissions=grant.permissions, recursive=grant.recursive,
    ) for grant in before.grants)
    saved = await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
        recipient_type="group", expected_revision=before.revision, grants=policies,
    ))
    assert saved == before
    omitted_policies = tuple(ShareNodePolicy(
        recipient=policy.recipient, permissions=policy.permissions,
    ) for policy in policies)
    assert await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
        recipient_type="group", expected_revision=saved.revision, grants=omitted_policies,
    )) == before
    for recursive in (True, False):
        policies = (policies[0].model_copy(update={"recursive": recursive}), policies[1])
        updated = await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
            recipient_type="group", expected_revision=saved.revision, grants=policies,
        ))
        assert updated.revision != saved.revision
        assert tuple(grant.recursive for grant in updated.grants) == (recursive, False)
        saved = updated
    assert (await context.namespace.get_node(context.node.id)) == context.node
