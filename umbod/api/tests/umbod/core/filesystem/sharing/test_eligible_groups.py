from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType, SYSTEM_ROOT_OWNER
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.sharing import EligibleSharingGroup, EligibleSharingGroups
from umbod.core.filesystem.stores.access_control import SessionAccessControl
from umbod.core.groups import RegisterGroupMetadata, UpdateGroupMetadata
from umbod.core.groups.stores.schema import GROUP_TABLE, PermissionGroupRecord
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.core.persistence import InsertCommand, TransactionMode
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot

from .conftest import SharingContext
from .test_policy import principal


@pytest.mark.asyncio
async def test_catalogue_preserves_exact_ids_and_metadata_without_membership_or_registration(
    context: SharingContext,
) -> None:
    identifiers = ("team", " Team ", "Team", "a/b")
    for identifier in identifiers:
        await context.groups.register_group_metadata(RegisterGroupMetadata(
            group_id=identifier, label="Label " + identifier, description="Managed collaboration group",
        ))
    await DatabaseIdentityDirectory(context.database).observe(IdentityObservation(
        issuer="issuer", subject="private-subject", claim="groups", groups=("observed-only",),
        name="Private Name", email="private@example.test", email_verification="verified",
        observed_at=datetime.now(timezone.utc),
    ))
    before = await context.service.inspect(caller(), context.node.id)
    result = await context.service.eligible_groups(caller(), context.node.id)
    assert result == EligibleSharingGroups(groups=tuple(
        EligibleSharingGroup(group_id=value, label=("Label " + value).strip(), description="Managed collaboration group")
        for value in sorted(identifiers)
    ))
    assert await context.service.inspect(caller(), context.node.id) == before
    assert {group.group_id for group in await context.groups.list_groups()} == set(identifiers)
    serialized = result.model_dump_json()
    for secret in ("revision", "issuer", "private", "email", "token", "observed-only"):
        assert secret not in serialized


@pytest.mark.asyncio
async def test_existing_editable_group_remains_eligible_and_metadata_does_not_change_policy_revision(
    context: SharingContext,
) -> None:
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=principal("team"), permissions={Permission.READ}, recursive=False,
    ))
    before = await context.service.inspect(caller(), context.node.id)
    await context.groups.update_group_metadata("team", UpdateGroupMetadata(
        expected_revision=1, label="Updated label", description="Updated description",
    ))
    result = await context.service.eligible_groups(caller(), context.node.id)
    assert result.groups == (EligibleSharingGroup(
        group_id="team", label="Updated label", description="Updated description",
    ),)
    assert await context.service.inspect(caller(), context.node.id) == before


@pytest.mark.asyncio
async def test_only_registered_nonblank_unblocked_recipients_are_returned(context: SharingContext) -> None:
    for identifier in ("foreign", "user", "system", "editable"):
        await context.groups.register_group_metadata(RegisterGroupMetadata(
            group_id=identifier, label=identifier, description="",
        ))
    for target, permissions, recursive in (
        (Principal(type=PrincipalType.GROUP, issuer="foreign", id="foreign"), {Permission.READ}, False),
        (Principal(type=PrincipalType.USER, issuer="issuer", id="user"), {Permission.READ}, False),
        (SYSTEM_ROOT_OWNER, {Permission.READ}, False),
        (principal("recursive"), {Permission.READ}, True),
        (principal("empty"), set(), False),
        (principal(" \t"), {Permission.READ}, False),
        (principal("editable"), {Permission.READ}, False),
    ):
        await context.policies.add_grant(AccessGrant(
            node_id=context.node.id, principal=target, permissions=permissions, recursive=recursive,
        ))
    async with context.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await SessionAccessControl(session).upsert_registered_grant(AccessGrant(
            node_id=context.node.id, principal=principal("orphan"), permissions={Permission.READ}, recursive=False,
        ))
        await session.insert(GROUP_TABLE, InsertCommand(row=PermissionGroupRecord(
            group_id="", label="Legacy blank", description="", revision=1,
        )))
    result = await context.service.eligible_groups(caller(), context.node.id)
    assert tuple(group.group_id for group in result.groups) == ("editable", "foreign", "system", "user")


@pytest.mark.asyncio
async def test_group_sharing_authority_can_select_groups_outside_membership(context: SharingContext) -> None:
    await context.groups.register_group_metadata(RegisterGroupMetadata(
        group_id="recipient", label="Recipient", description="",
    ))
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=principal("sharers"),
        permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
    ))
    result = await context.service.eligible_groups(snapshot("bob", "issuer", ("sharers",)), context.node.id)
    assert {group.group_id for group in result.groups} == {"recipient", "sharers"}


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.SHARE}])
async def test_missing_or_unauthorized_target_is_indistinguishable(
    context: SharingContext, permissions: set[Permission],
) -> None:
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=principal("admins"), permissions=permissions, recursive=False,
    ))
    for node_id in (context.node.id, uuid4()):
        with pytest.raises(PermissionDenied):
            await context.service.eligible_groups(snapshot("admin", "issuer", ("admins",)), node_id)


@pytest.mark.parametrize("identifier", ["", " \t"])
def test_eligible_models_reject_blank_identifiers(identifier: str) -> None:
    with pytest.raises(ValidationError):
        EligibleSharingGroup(group_id=identifier, label="Label", description="")


def test_eligible_models_are_frozen_and_forbid_private_fields() -> None:
    group = EligibleSharingGroup(group_id=" Exact ", label="Label", description="")
    with pytest.raises(ValidationError):
        group.group_id = "changed"
    groups = EligibleSharingGroups(groups=(group,))
    with pytest.raises(ValidationError):
        groups.groups = ()
    with pytest.raises(ValidationError):
        EligibleSharingGroup.model_validate({**group.model_dump(), "revision": 1})
