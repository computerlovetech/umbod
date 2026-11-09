from tests.support.filesystem.sharing_policy import GROUP_SCOPE
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType, SYSTEM_ROOT_OWNER
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.sharing import (
    EligibleSharingGroup, EligibleSharingGroups, GroupSharingRecipient,
    SharingRecipientSearchQuery, SharingRecipientSearchResult,
)
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


def group_search(query: str) -> SharingRecipientSearchQuery:
    return SharingRecipientSearchQuery(query=query, scope=GROUP_SCOPE)


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
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    result = await context.service.search_recipients(caller(), context.node.id, group_search("Label"))
    assert result == SharingRecipientSearchResult(recipients=tuple(
        GroupSharingRecipient(type="group", group_id=value, label=("Label " + value).strip())
        for value in sorted(identifiers, key=lambda value: (" ".join(("Label " + value).split()).casefold(), value))
    ), has_more=False)
    assert await context.service.inspect(caller(), context.node.id, GROUP_SCOPE) == before
    assert {group.group_id for group in await context.groups.list_groups()} == set(identifiers)
    serialized = result.model_dump_json()
    for secret in ("revision", "issuer", "private", "email", "token", "observed-only", "description", "Managed collaboration"):
        assert secret not in serialized


@pytest.mark.asyncio
async def test_existing_editable_group_remains_eligible_and_metadata_does_not_change_policy_revision(
    context: SharingContext,
) -> None:
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=principal("team"), permissions={Permission.READ}, recursive=False,
    ))
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    await context.groups.update_group_metadata("team", UpdateGroupMetadata(
        expected_revision=1, label="Updated label", description="Updated description",
    ))
    result = await context.service.search_recipients(caller(), context.node.id, group_search("Updated"))
    assert result == SharingRecipientSearchResult(recipients=(GroupSharingRecipient(
        type="group", group_id="team", label="Updated label",
    ),), has_more=False)
    assert "description" not in result.model_dump_json()
    after = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    assert after.revision == before.revision
    assert after.grants[0].permissions == before.grants[0].permissions
    assert after.grants[0].recipient.label == "Updated label"


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
    recipients: set[str] = set()
    for query in ("foreign", "user", "system", "editable", "recursive", "empty", "orphan", "Legacy blank"):
        result = await context.service.search_recipients(caller(), context.node.id, group_search(query))
        assert not result.has_more
        recipients.update(recipient.group_id for recipient in result.recipients)
    assert recipients == {"editable", "foreign", "recursive", "system", "user"}


@pytest.mark.asyncio
async def test_group_sharing_authority_can_select_groups_outside_membership(context: SharingContext) -> None:
    await context.groups.register_group_metadata(RegisterGroupMetadata(
        group_id="recipient", label="Recipient", description="",
    ))
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=principal("sharers"),
        permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
    ))
    recipients: set[str] = set()
    for query in ("recipient", "sharers"):
        result = await context.service.search_recipients(
            snapshot("bob", "issuer", ("sharers",)), context.node.id, group_search(query),
        )
        assert not result.has_more
        recipients.update(recipient.group_id for recipient in result.recipients)
    assert recipients == {"recipient", "sharers"}


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
            await context.service.search_recipients(
                snapshot("admin", "issuer", ("admins",)), node_id, group_search("admins"),
            )


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
