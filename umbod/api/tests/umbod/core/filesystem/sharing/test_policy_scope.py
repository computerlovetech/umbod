import asyncio

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType, RevisionConflict
from umbod.core.filesystem.sharing import (
    GroupSharingTarget, InvalidSharingPolicy, ReplaceNodePolicy, SharingScope,
    ShareNodePolicy, UserSharingTarget,
)
from tests.support.filesystem.sharing_policy import GROUP_SCOPE
from tests.umbod.core.filesystem.test_authorized_content import caller
from .test_user_policy import UserContext, observation, observe, user_command
from .test_user_policy import user_context as user_context


USER_SCOPE = SharingScope(recipient_types=frozenset({"user"}))
ALL_SCOPE = SharingScope(recipient_types=frozenset({"group", "user"}))


def team_command() -> ShareNodePolicy:
    return ShareNodePolicy(
        recipient=GroupSharingTarget(type="group", group_id="team"),
        permissions=frozenset({Permission.WRITE}),
    )


@pytest.mark.asyncio
async def test_read_scope_changes_only_projection_and_summary_uses_same_projection(user_context: UserContext) -> None:
    context = user_context
    identifier = await observe(context.directory, "issuer", " recipient ")
    await context.service.share(caller(), context.node.id, user_command(identifier, Permission.READ))
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="team"),
        permissions={Permission.WRITE}, recursive=False,
    ))
    combined = await asyncio.wait_for(context.service.inspect(caller(), context.node.id, ALL_SCOPE), 3)
    groups = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    users = await context.service.inspect(caller(), context.node.id, USER_SCOPE)
    assert combined.revision == groups.revision == users.revision
    assert combined.grants == groups.grants + users.grants
    assert tuple(grant.recipient.type for grant in combined.grants) == ("group", "user")
    summary = (await context.service.summarize_nodes(caller(), (context.node.id,))).nodes[0]
    assert summary.can_share and summary.grants == combined.grants
    assert users.grants[0].recipient.user_id == identifier
    assert set(users.grants[0].recipient.model_dump()) == {"type", "user_id", "label"}


@pytest.mark.asyncio
@pytest.mark.parametrize("selected_type", ["group", "user"])
async def test_replacement_changes_selected_type_only_and_empty_clear_preserves_protected_policy(
    user_context: UserContext, selected_type: str,
) -> None:
    context = user_context
    identifier = await observe(context.directory, "issuer", " recipient ")
    await context.service.share(caller(), context.node.id, user_command(identifier, Permission.READ))
    group = team_command()
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="team"),
        permissions=set(group.permissions), recursive=False,
    ))
    protected = tuple(AccessGrant(
        node_id=context.node.id, principal=principal, permissions=set(), recursive=recursive,
    ) for principal, recursive in (
        (Principal(type=PrincipalType.USER, issuer="foreign", id=" recipient "), False),
        (Principal(type=PrincipalType.USER, issuer="issuer", id="unknown"), False),
        (Principal(type=PrincipalType.USER, issuer="issuer", id="recursive"), True),
        (Principal(type=PrincipalType.SYSTEM, issuer="issuer", id="system"), False),
        (Principal(type=PrincipalType.GROUP, issuer="issuer", id="recursive"), True),
    ))
    for grant in protected:
        await context.policies.add_grant(grant)
    before = await context.service.inspect(caller(), context.node.id, ALL_SCOPE)
    requested = (
        user_command(identifier, Permission.DISCOVER, Permission.WRITE)
        if selected_type == "user" else ShareNodePolicy(recipient=group.recipient, permissions=frozenset({Permission.READ}))
    )
    saved = await asyncio.wait_for(context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
        recipient_type=selected_type, expected_revision=before.revision, grants=(requested,),
    )), 3)
    assert len(saved.grants) == 1
    assert saved.grants[0].recipient.type == selected_type
    assert saved.grants[0].permissions == requested.permissions
    cleared = await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
        recipient_type=selected_type, expected_revision=saved.revision, grants=(),
    ))
    assert cleared.grants == ()
    remaining = await context.policies.list_grants(context.node.id)
    assert all(grant in remaining for grant in protected)
    other_type = PrincipalType.GROUP if selected_type == "user" else PrincipalType.USER
    other = next(grant for grant in remaining if grant.principal.type == other_type and grant.principal.id in ("team", " recipient ") and grant.principal.issuer == "issuer")
    assert other.permissions == (set(group.permissions) if selected_type == "user" else {Permission.READ})
    assert await context.namespace.get_node(context.node.id) == context.node


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive,permissions", [(True, set()), (False, set())])
async def test_user_replacement_reports_and_rejects_known_protected_collisions(
    user_context: UserContext, recursive: bool, permissions: set[Permission],
) -> None:
    context = user_context
    identifier = await observe(context.directory, "issuer", "recipient")
    grant = AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="recipient"),
        permissions=permissions, recursive=recursive,
    )
    await context.policies.add_grant(grant)
    view = await context.service.inspect(caller(), context.node.id, USER_SCOPE)
    assert view.grants == ()
    assert view.blocked_recipients == (UserSharingTarget(type="user", user_id=identifier),)
    with pytest.raises(InvalidSharingPolicy):
        await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
            recipient_type="user", expected_revision=view.revision, grants=(user_command(identifier, Permission.WRITE),),
        ))
    await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
        recipient_type="user", expected_revision=view.revision, grants=(),
    ))
    assert await context.policies.list_grants(context.node.id) == [grant]


@pytest.mark.asyncio
async def test_user_resolution_eligibility_changes_whole_policy_revision_but_labels_do_not(user_context: UserContext) -> None:
    context = user_context
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="recipient"),
        permissions={Permission.READ}, recursive=False,
    ))
    unresolved = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    await observe(context.directory, "issuer", "recipient")
    resolved = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    assert resolved.revision != unresolved.revision
    with pytest.raises(RevisionConflict):
        await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(
            recipient_type="group", expected_revision=unresolved.revision, grants=(),
        ))
    await context.directory.observe(observation("issuer", "recipient", "Renamed"))
    renamed = await context.service.inspect(caller(), context.node.id, USER_SCOPE)
    assert renamed.revision == resolved.revision
    assert renamed.grants[0].recipient.label == "Renamed"


@pytest.mark.parametrize("recipient_type,grants", [
    ("user", (team_command(),)),
    ("group", (user_command("opaque", Permission.READ),)),
    ("group", (team_command(), team_command())),
    ("user", (user_command("opaque", Permission.READ), user_command("opaque", Permission.WRITE))),
])
def test_replacement_rejects_duplicate_and_mismatched_typed_targets_before_io(
    recipient_type: str, grants: tuple[ShareNodePolicy, ...],
) -> None:
    with pytest.raises(ValidationError):
        ReplaceNodePolicy(recipient_type=recipient_type, expected_revision="r", grants=grants)


@pytest.mark.parametrize("scope", [frozenset(), frozenset({"system"}), ["group"], {"group"}])
def test_sharing_scope_requires_a_nonempty_strict_frozen_recipient_set(scope: object) -> None:
    with pytest.raises(ValidationError):
        SharingScope(recipient_types=scope)


def test_sharing_scope_is_frozen_and_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GROUP_SCOPE.recipient_types = frozenset({"user"})
    with pytest.raises(ValidationError):
        SharingScope.model_validate({"recipient_types": frozenset({"group"}), "issuer": "foreign"})
