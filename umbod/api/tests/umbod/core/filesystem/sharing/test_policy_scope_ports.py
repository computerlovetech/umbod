from uuid import uuid4

import pytest

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, NodeId, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from tests.support.filesystem.group_sharing import SharingPolicies, sharing_node
from tests.support.identity_directory import InMemoryIdentityDirectory
from umbod.core.identity_directory.user_models import ObservedUserProfile, SubjectUsersLookup
from umbod.core.filesystem.sharing import InvalidSharingPolicy, ReplaceNodePolicy, SharingService
from tests.support.filesystem.sharing_policy import GROUP_SCOPE
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .test_policy_scope import ALL_SCOPE, USER_SCOPE
from .test_ports import transactions
from .test_user_policy import observation, observe, user_command
from .test_user_ports import UnreadableUsers
from .test_user_summaries import CountingUsers, ExplicitLocalResolver


class MutationGuardPolicies(SharingPolicies):
    def __init__(self, ownership: Ownership, grants: tuple[AccessGrant, ...]) -> None:
        super().__init__(ownership, grants)
        self.mutations_allowed = True

    def reject_mutations(self) -> None:
        self.mutations_allowed = False

    async def remove_grant(self, node_id: NodeId, principal: Principal) -> None:
        if not self.mutations_allowed:
            raise AssertionError("Mutation preceded complete target validation")
        await super().remove_grant(node_id, principal)

    async def upsert(self, grant: AccessGrant) -> None:
        if not self.mutations_allowed:
            raise AssertionError("Mutation preceded complete target validation")
        await super().upsert(grant)


class RebindingUsers(InMemoryIdentityDirectory):
    def __init__(self) -> None:
        super().__init__()
        self.bindings: dict[tuple[str, str], str] = {}

    def rebind(self, issuer: str, subject: str, user_id: str) -> None:
        self.bindings[issuer, subject] = user_id

    async def find_subject_users(self, lookup: SubjectUsersLookup) -> tuple[ObservedUserProfile, ...]:
        profiles = await super().find_subject_users(lookup)
        return tuple(
            profile.model_copy(update={"user_id": self.bindings[profile.issuer, profile.subject]})
            if (profile.issuer, profile.subject) in self.bindings else profile
            for profile in profiles
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("has_user_grant", [False, True])
@pytest.mark.parametrize("provenance", [AuthenticationProvenance.LOCAL_SIMULATION, AuthenticationProvenance.UPSTREAM_VERIFIED])
async def test_directory_unauthorized_callers_cannot_project_or_clear_users_even_when_scope_is_empty(
    has_user_grant: bool, provenance: AuthenticationProvenance,
) -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    node_id = sharing_node().id
    if has_user_grant:
        await ports.policies.add_grant(AccessGrant(
            node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="recipient"),
            permissions={Permission.READ}, recursive=False,
        ))
    actor = snapshot("alice", "foreign" if provenance == AuthenticationProvenance.UPSTREAM_VERIFIED else "issuer", ())
    actor = actor.model_copy(update={"caller": actor.caller.model_copy(update={"authentication": provenance})})
    service = SharingService(ExplicitLocalResolver(), ports, "issuer")
    before = await ports.policies.list_grants(node_id)
    view = await service.inspect(actor, node_id, ALL_SCOPE)
    assert view.grants == view.blocked_recipients == ()
    with pytest.raises(PermissionDenied):
        await service.replace(actor, node_id, ReplaceNodePolicy(
            recipient_type="user", expected_revision=view.revision, grants=(),
        ))
    await service.replace(actor, node_id, ReplaceNodePolicy(
        recipient_type="group", expected_revision=view.revision, grants=(),
    ))
    assert await ports.policies.list_grants(node_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.SHARE}, {Permission.DISCOVER}, {Permission.READ, Permission.WRITE}])
async def test_inspection_and_replacement_authorize_node_before_any_directory_lookup(permissions: set[Permission]) -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    node_id = sharing_node().id
    await ports.policies.add_grant(AccessGrant(
        node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="delegate"),
        permissions=permissions, recursive=False,
    ))
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    actor = snapshot("delegate", "issuer", ())
    for target in (node_id, uuid4()):
        with pytest.raises(PermissionDenied):
            await service.inspect(actor, target, USER_SCOPE)
        with pytest.raises(PermissionDenied):
            await service.replace(actor, target, ReplaceNodePolicy(
                recipient_type="user", expected_revision="stale", grants=(user_command("unknown", Permission.READ),),
            ))


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_target", ["unknown", "foreign"])
async def test_all_user_targets_resolve_before_any_mutation(invalid_target: str) -> None:
    ports = transactions()
    policies = MutationGuardPolicies(await ports.policies.get_owner(sharing_node().id), ())
    ports.policies = policies
    identifier = await observe(ports.users, "issuer", "recipient")
    invalid_identifier = await observe(ports.users, "foreign", "recipient") if invalid_target == "foreign" else "unknown"
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    node_id = sharing_node().id
    await service.share(caller(), node_id, user_command(identifier, Permission.READ))
    view = await service.inspect(caller(), node_id, USER_SCOPE)

    policies.reject_mutations()
    with pytest.raises(InvalidSharingPolicy):
        await service.replace(caller(), node_id, ReplaceNodePolicy(
            recipient_type="user", expected_revision=view.revision,
            grants=(user_command(identifier, Permission.WRITE), user_command(invalid_identifier, Permission.READ)),
        ))


@pytest.mark.asyncio
async def test_inspect_without_users_never_reads_directory_but_group_filtered_users_use_one_profile_batch() -> None:
    ports = transactions()
    users = CountingUsers()
    ports.users = users
    node_id = sharing_node().id
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    await service.inspect(caller(), node_id, GROUP_SCOPE)
    assert users.lookups == []
    for subject in ("first", "second"):
        await users.observe(observation("issuer", subject, subject))
        await ports.policies.add_grant(AccessGrant(
            node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id=subject),
            permissions={Permission.READ}, recursive=False,
        ))
    await service.inspect(caller(), node_id, GROUP_SCOPE)
    assert len(users.lookups) == 1
    assert users.lookups[0].subjects == frozenset({"first", "second"})


@pytest.mark.asyncio
async def test_user_binding_changes_revision_without_changing_grants() -> None:
    ports = transactions()
    users = RebindingUsers()
    ports.users = users
    identifier = await observe(users, "issuer", "recipient")
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    node_id = sharing_node().id
    await service.share(caller(), node_id, user_command(identifier, Permission.READ))
    before = await service.inspect(caller(), node_id, GROUP_SCOPE)
    users.rebind("issuer", "recipient", "new-opaque-id")
    after = await service.inspect(caller(), node_id, GROUP_SCOPE)
    assert after.revision != before.revision
