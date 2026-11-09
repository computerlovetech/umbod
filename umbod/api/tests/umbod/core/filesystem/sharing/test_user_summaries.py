from uuid import uuid4

import pytest

from umbod.core.callers import AuthenticationProvenance, CallerSnapshot
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, ResolvedIdentity, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import initial_root
from umbod.core.filesystem.sharing import SharingService
from umbod.core.identity_directory.user_models import ObservedUserProfile, SubjectUsersLookup
from tests.support.identity_directory import InMemoryIdentityDirectory
from tests.umbod.core.filesystem.test_authorized_content import alice, caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .test_additive_policy import command
from .test_ports import transactions
from .test_user_policy import UserContext, observation, observe, user_command
from .test_user_policy import user_context as user_context
from .test_user_ports import UnreadableUsers


class CountingUsers(InMemoryIdentityDirectory):
    def __init__(self) -> None:
        super().__init__()
        self.lookups: list[SubjectUsersLookup] = []

    async def find_subject_users(self, lookup: SubjectUsersLookup) -> tuple[ObservedUserProfile, ...]:
        self.lookups.append(lookup)
        return await super().find_subject_users(lookup)


class ExplicitLocalResolver:
    async def resolve(self, snapshot: CallerSnapshot) -> ResolvedIdentity:
        return ResolvedIdentity(user=alice(), groups=frozenset())


@pytest.mark.asyncio
async def test_combined_summaries_preserve_groups_and_append_sorted_current_user_labels(user_context: UserContext) -> None:
    context = user_context
    identifiers = [await observe(context.directory, "issuer", subject) for subject in ("first", "second")]
    for identifier in identifiers:
        await context.service.share(caller(), context.node.id, user_command(identifier, Permission.READ))
    await context.directory.observe(observation("issuer", "first", "Current label"))
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="team"),
        permissions={Permission.WRITE}, recursive=False,
    ))
    for target in (
        Principal(type=PrincipalType.USER, issuer="foreign", id="first"),
        Principal(type=PrincipalType.USER, issuer="issuer", id="unknown"),
    ):
        await context.policies.add_grant(AccessGrant(
            node_id=context.node.id, principal=target, permissions={Permission.READ}, recursive=False,
        ))
    result = await context.service.summarize_nodes(caller(), (context.node.id, uuid4()))
    summary = result.nodes[0]
    assert summary.can_share
    assert summary.grants[0].recipient.type == "group"
    assert summary.grants[0].recipient.group_id == "team"
    users = summary.grants[1:]
    assert [grant.recipient.user_id for grant in users] == sorted(identifiers)
    assert {grant.recipient.user_id: grant.recipient.label for grant in users} == {
        identifiers[0]: "Current label", identifiers[1]: "Display Name",
    }
    assert all(set(grant.recipient.model_dump()) == {"type", "user_id", "label"} for grant in users)
    assert result.nodes[1].model_dump(mode="json") == {
        "node_id": str(result.nodes[1].node_id), "can_share": False,
    }


@pytest.mark.asyncio
async def test_batch_reverse_lookup_reads_once_for_all_authorized_nodes_only() -> None:
    ports = transactions()
    users = CountingUsers()
    ports.users = users
    root = initial_root()
    second = root.model_copy(update={"id": uuid4(), "parent_id": root.id})
    restricted = root.model_copy(update={"id": uuid4(), "parent_id": root.id})
    for node in (second, restricted):
        ports.namespace.nodes[node.id] = node
    ports.policies.owners[second.id] = ports.policies.owners[root.id].model_copy(update={"node_id": second.id})
    ports.policies.owners[restricted.id] = ports.policies.owners[root.id].model_copy(update={
        "node_id": restricted.id, "owner": Principal(type=PrincipalType.USER, issuer="issuer", id="other"),
    })
    for node, subject in ((root, "first"), (second, "second"), (restricted, "secret")):
        await users.observe(observation("issuer", subject, subject))
        await ports.policies.add_grant(AccessGrant(
            node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id=subject),
            permissions={Permission.READ}, recursive=False,
        ))
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    result = await service.summarize_nodes(caller(), (root.id, second.id, restricted.id, root.id))
    assert [node.can_share for node in result.nodes] == [True, True, False]
    assert users.lookups == [SubjectUsersLookup(issuer="issuer", subjects=frozenset({"first", "second"}))]


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [AuthenticationProvenance.LOCAL_SIMULATION, AuthenticationProvenance.UPSTREAM_VERIFIED])
async def test_group_summaries_survive_inapplicable_user_lookup_without_directory_reads(provenance: AuthenticationProvenance) -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    root = initial_root()
    await ports.policies.add_grant(AccessGrant(
        node_id=root.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="recipient"),
        permissions={Permission.READ}, recursive=False,
    ))
    service = SharingService(ExplicitLocalResolver(), ports, "issuer")
    actor = snapshot("alice", "foreign" if provenance == AuthenticationProvenance.UPSTREAM_VERIFIED else "issuer", ())
    actor = actor.model_copy(update={"caller": actor.caller.model_copy(update={"authentication": provenance})})
    await service.share(actor, root.id, command("team", Permission.WRITE))
    summary = (await service.summarize_nodes(actor, (root.id,))).nodes[0]
    assert summary.can_share and [grant.recipient.type for grant in summary.grants] == ["group"]
    with pytest.raises(PermissionDenied):
        await service.share(actor, root.id, user_command("opaque", Permission.READ))


@pytest.mark.asyncio
async def test_unverified_caller_with_default_resolver_is_denied_before_directory_reads() -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    actor = caller()
    actor = actor.model_copy(update={"caller": actor.caller.model_copy(update={
        "authentication": AuthenticationProvenance.LOCAL_SIMULATION,
    })})
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    with pytest.raises(PermissionDenied):
        await service.summarize_nodes(actor, (initial_root().id,))
    with pytest.raises(PermissionDenied):
        await service.share(actor, initial_root().id, user_command("opaque", Permission.READ))
