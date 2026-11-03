from tests.support.filesystem.sharing_policy import GROUP_SCOPE, group_commands
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

import pytest
import pytest_asyncio

from umbod.core.filesystem import (
    AccessControlDriver, AccessGrant, NamespaceDriver, Node, Permission, Principal,
    PrincipalType, RevisionConflict,
)
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.sharing import (
    FilesystemSharing, InvalidSharingPolicy, ReplaceNodePolicy, ShareNodePolicy, UserSharingTarget,
)
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.ports import IdentityDirectoryStore, ObservedUserDirectory
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.core.identity_directory.user_models import SubjectUsersLookup
from tests.persistence_runtime import prepared_inmemory_runtime
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import sharing_context


class UserDirectory(IdentityDirectoryStore, ObservedUserDirectory, Protocol):
    pass


@dataclass(frozen=True)
class UserContext:
    service: FilesystemSharing
    directory: UserDirectory
    policies: AccessControlDriver
    namespace: NamespaceDriver
    node: Node


def observation(issuer: str, subject: str, name: str) -> IdentityObservation:
    return IdentityObservation(
        issuer=issuer, subject=subject, claim="groups", groups=(), name=name,
        email="private@example.test", email_verification="verified",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


async def observe(directory: UserDirectory, issuer: str, subject: str) -> str:
    await directory.observe(observation(issuer, subject, "Display Name"))
    profiles = await directory.find_subject_users(SubjectUsersLookup(issuer=issuer, subjects=frozenset({subject})))
    return profiles[0].user_id


def user_command(user_id: str, *permissions: Permission) -> ShareNodePolicy:
    return ShareNodePolicy(
        recipient=UserSharingTarget(type="user", user_id=user_id), permissions=frozenset(permissions),
    )


@pytest_asyncio.fixture
async def user_context() -> AsyncIterator[UserContext]:
    runtime = await prepared_inmemory_runtime()
    try:
        context = await sharing_context(runtime.database)
        yield UserContext(
            context.service, DatabaseIdentityDirectory(runtime.database), context.policies,
            context.namespace, context.node,
        )
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_user_share_unions_and_repeats_without_changing_ownership_or_node(user_context: UserContext) -> None:
    context = user_context
    user_id = await observe(context.directory, "issuer", " recipient ")
    before = await context.policies.get_owner(context.node.id)
    first = await asyncio.wait_for(context.service.share(caller(), context.node.id, user_command(user_id, Permission.READ)), 3)
    assert first.changed and first.permissions == frozenset({Permission.READ})
    added = await context.service.share(caller(), context.node.id, user_command(user_id, Permission.WRITE))
    assert added.changed and added.permissions == frozenset({Permission.READ, Permission.WRITE})
    repeated = await context.service.share(caller(), context.node.id, user_command(user_id, Permission.READ))
    assert not repeated.changed and repeated.permissions == added.permissions
    grants = await context.policies.list_grants(context.node.id)
    assert grants == [AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id=" recipient "),
        permissions={Permission.READ, Permission.WRITE}, recursive=False,
    )]
    summary = (await asyncio.wait_for(context.service.summarize_nodes(caller(), (context.node.id,)), 3)).nodes[0]
    assert summary.can_share
    assert summary.grants[0].recipient.model_dump() == {
        "type": "user", "user_id": user_id, "label": "Display Name",
    }
    assert summary.grants[0].permissions == added.permissions
    assert first.recipient == user_command(user_id, Permission.READ).recipient
    assert await context.policies.get_owner(context.node.id) == before
    assert await context.namespace.get_node(context.node.id) == context.node


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive,permissions", [(True, {Permission.READ}), (False, set())])
async def test_known_protected_user_collisions_block_share_and_summary(user_context: UserContext, recursive: bool, permissions: set[Permission]) -> None:
    context = user_context
    user_id = await observe(context.directory, "issuer", "recipient")
    grant = AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="recipient"),
        permissions=permissions, recursive=recursive,
    )
    await context.policies.add_grant(grant)
    before = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    summary = (await context.service.summarize_nodes(caller(), (context.node.id,))).nodes[0]
    assert summary.can_share and summary.grants == ()
    with pytest.raises(InvalidSharingPolicy):
        await context.service.share(caller(), context.node.id, user_command(user_id, Permission.WRITE))
    assert await context.policies.list_grants(context.node.id) == [grant]
    assert await context.service.inspect(caller(), context.node.id, GROUP_SCOPE) == before


@pytest.mark.asyncio
async def test_unknown_foreign_and_inexact_ids_are_sanitized_and_do_not_mutate(user_context: UserContext) -> None:
    context = user_context
    user_id = await observe(context.directory, "issuer", "recipient")
    foreign = await observe(context.directory, "foreign", "recipient")
    for identifier in ("missing", "recipient", "Display Name", "private@example.test", foreign, " " + user_id, user_id.upper()):
        with pytest.raises(InvalidSharingPolicy) as failure:
            await context.service.share(caller(), context.node.id, user_command(identifier, Permission.READ))
        assert identifier not in str(failure.value)
    assert await context.policies.list_grants(context.node.id) == []


@pytest.mark.asyncio
async def test_user_mutations_invalidate_group_revision_and_fresh_replacement_preserves_all_users(user_context: UserContext) -> None:
    context = user_context
    user_id = await observe(context.directory, "issuer", "recipient")
    protected = [AccessGrant(
        node_id=context.node.id, principal=principal, permissions={Permission.READ}, recursive=False,
    ) for principal in (
        Principal(type=PrincipalType.USER, issuer="foreign", id="recipient"),
        Principal(type=PrincipalType.USER, issuer="issuer", id="unknown-subject"),
        Principal(type=PrincipalType.SYSTEM, issuer="issuer", id="service"),
    )]
    for grant in protected:
        await context.policies.add_grant(grant)
    stale = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    await context.service.share(caller(), context.node.id, user_command(user_id, Permission.READ))
    with pytest.raises(RevisionConflict):
        await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=stale.revision, grants=group_commands(())))
    before = await context.policies.list_grants(context.node.id)
    fresh = await context.service.inspect(caller(), context.node.id, GROUP_SCOPE)
    await context.service.replace(caller(), context.node.id, ReplaceNodePolicy(recipient_type="group", expected_revision=fresh.revision, grants=group_commands(())))
    assert await context.policies.list_grants(context.node.id) == before
    summary = (await context.service.summarize_nodes(caller(), (context.node.id,))).nodes[0]
    assert summary.can_share
    assert tuple(grant.recipient.user_id for grant in summary.grants) == (user_id,)

@pytest.mark.asyncio
async def test_missing_or_inaccessible_user_operations_deny(user_context: UserContext) -> None:
    context = user_context
    actor = snapshot("administrator", "issuer", ("admins",))
    for node_id in (context.node.id, uuid4()):
        with pytest.raises(PermissionDenied):
            await context.service.share(actor, node_id, user_command("unknown", Permission.READ))
