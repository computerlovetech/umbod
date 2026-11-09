from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import initial_root
from umbod.core.filesystem.sharing import (
    GroupSharingRecipient, SharingRecipientSearchQuery, SharingRecipientType,
    SharingScope, SharingService, UserSharingRecipient,
)
from umbod.core.groups import RegisterGroupMetadata
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.core.identity_directory.user_models import ScopedUserSearch, UserLookup, UserSearchPage
from tests.support.identity_directory import InMemoryIdentityDirectory
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import SharingContext
from .test_ports import transactions
from .test_user_policy import UserContext, observation, user_context

__all__ = ["user_context"]


def search(query: str, types: frozenset[SharingRecipientType]) -> SharingRecipientSearchQuery:
    return SharingRecipientSearchQuery(query=query, scope=SharingScope(recipient_types=types))


BOTH = frozenset({"group", "user"})
GROUP = frozenset({"group"})
USER = frozenset({"user"})


class CountingUsers(InMemoryIdentityDirectory):
    def __init__(self) -> None:
        super().__init__()
        self.searches: list[ScopedUserSearch] = []

    async def search_user_names(self, search: ScopedUserSearch) -> UserSearchPage:
        self.searches.append(search)
        return await super().search_user_names(search)

    async def find_user_identity(self, lookup: UserLookup) -> None:
        raise AssertionError("Search must not resolve individual users")


class UnreadableUsers(InMemoryIdentityDirectory):
    async def search_user_names(self, search: ScopedUserSearch) -> UserSearchPage:
        raise AssertionError("Directory must not be accessed")


@pytest.mark.asyncio
@pytest.mark.parametrize("types", [GROUP, USER, BOTH])
async def test_mixed_results_filter_by_type_with_minimal_labelled_targets(
    context: SharingContext, types: frozenset[SharingRecipientType],
) -> None:
    await context.groups.register_group_metadata(RegisterGroupMetadata(
        group_id="exact-id", label="Ada  Lovelace", description="private-description",
    ))
    directory = DatabaseIdentityDirectory(context.database)
    await directory.observe(observation("issuer", "private-subject", "ADA Lovelace"))
    await directory.observe(observation("foreign", "foreign-subject", "Ada Lovelace"))
    before = await context.policies.list_grants(context.node.id)
    result = await context.service.search_recipients(caller(), context.node.id, search("  aDa   LoVELace ", types))
    assert tuple(recipient.type for recipient in result.recipients) == tuple(sorted(types))
    assert not result.has_more
    for recipient in result.recipients:
        assert set(recipient.model_dump()) == {"type", "label", "group_id" if recipient.type == "group" else "user_id"}
    serialized = result.model_dump_json()
    for private in ("private", "foreign", "issuer", "email", "subject", "description"):
        assert private not in serialized
    assert await context.policies.list_grants(context.node.id) == before
    assert await context.namespace.get_node(context.node.id) == context.node


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected", [("Exact", (" Exact%_ID ",)), ("%_", (" Exact%_ID ",)), ("alpha beta", ("label",)), ("%x", ())])
async def test_group_matching_is_normalized_literal_id_or_label_and_reuses_eligibility(
    context: SharingContext, text: str, expected: tuple[str, ...],
) -> None:
    for identifier, label in ((" Exact%_ID ", "Other"), ("label", "Alpha  Beta"), ("blocked", "Alpha Beta")):
        await context.groups.register_group_metadata(RegisterGroupMetadata(group_id=identifier, label=label, description=""))
    await context.policies.add_grant(AccessGrant(
        node_id=context.node.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="blocked"),
        permissions=set(), recursive=True,
    ))
    result = await context.service.search_recipients(caller(), context.node.id, search(text, GROUP))
    assert tuple(recipient.group_id for recipient in result.recipients) == expected
    assert all(recipient.group_id in {" Exact%_ID ", "label"} for recipient in result.recipients)
    assert all(recipient.group_id != "blocked" for recipient in result.recipients)
    assert not result.has_more


@pytest.mark.asyncio
@pytest.mark.parametrize("types", [GROUP, USER, BOTH])
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.SHARE}])
async def test_authority_precedes_all_catalogue_and_directory_reads_even_for_missing_nodes(
    types: frozenset[SharingRecipientType], permissions: set[Permission],
) -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    node_id = initial_root().id
    await ports.policies.add_grant(AccessGrant(
        node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="delegate"),
        permissions=permissions, recursive=False,
    ))
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    for target in (node_id, uuid4()):
        with pytest.raises(PermissionDenied):
            await service.search_recipients(snapshot("delegate", "issuer", ()), target, search("Ada", types))
    assert ports.groups.reads == 0


@pytest.mark.asyncio
async def test_group_only_search_never_reads_directory() -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    result = await service.search_recipients(caller(), initial_root().id, search("TEAM", GROUP))
    assert result.recipients == (GroupSharingRecipient(type="group", group_id="team", label="team"),)
    assert len(result.recipients) == 1
    assert not result.has_more


@pytest.mark.asyncio
@pytest.mark.parametrize("types", [USER, BOTH])
async def test_foreign_issuer_authority_fails_whole_search_without_group_partial(
    types: frozenset[SharingRecipientType],
) -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    await ports.policies.add_grant(AccessGrant(
        node_id=initial_root().id, principal=Principal(type=PrincipalType.USER, issuer="foreign", id="delegate"),
        permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
    ))
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    with pytest.raises(PermissionDenied):
        await service.search_recipients(snapshot("delegate", "foreign", ()), initial_root().id, search("team", types))


@pytest.mark.asyncio
@pytest.mark.parametrize("authentication", [AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.LOCAL_SIMULATION])
async def test_unverified_provenance_denies_before_discovery(authentication: AuthenticationProvenance) -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    actor = caller()
    actor = actor.model_copy(update={"caller": actor.caller.model_copy(update={"authentication": authentication})})
    with pytest.raises(PermissionDenied):
        await SharingService(VerifiedIdentityResolver(), ports, "issuer").search_recipients(actor, initial_root().id, search("team", BOTH))
    assert ports.groups.reads == 0


@pytest.mark.asyncio
async def test_fifty_protected_duplicate_names_do_not_hide_eligible_fifty_first_user(user_context: UserContext) -> None:
    context = user_context
    for index in range(51):
        subject = f"subject-{index:02}"
        await context.directory.observe(observation("issuer", subject, "Duplicate Name"))
        if index < 50:
            await context.policies.add_grant(AccessGrant(
                node_id=context.node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id=subject),
                permissions=set(), recursive=True,
            ))
    before = await context.policies.list_grants(context.node.id)
    result = await context.service.search_recipients(caller(), context.node.id, search("duplicate", USER))
    assert len(result.recipients) == 1
    assert not result.has_more
    assert isinstance(result.recipients[0], UserSharingRecipient)
    selected = await context.directory.find_user_identity(UserLookup(issuer="issuer", user_id=result.recipients[0].user_id))
    assert selected is not None and selected.subject == "subject-50"
    assert await context.policies.list_grants(context.node.id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("types", [GROUP, USER, BOTH])
async def test_fixed_global_limit_and_deterministic_groups_first_sort(
    context: SharingContext, types: frozenset[SharingRecipientType],
) -> None:
    directory = DatabaseIdentityDirectory(context.database)
    for index in range(51):
        await directory.observe(observation("issuer", str(index), f"Match {index:02}"))
        await context.groups.register_group_metadata(RegisterGroupMetadata(
            group_id=f"id-{index:02}", label=f"Match {50-index:02}", description="",
        ))
    result = await context.service.search_recipients(caller(), context.node.id, search("match", types))
    assert len(result.recipients) == 50 and result.has_more
    assert result == await context.service.search_recipients(caller(), context.node.id, search("match", types))
    assert tuple(recipient.label for recipient in result.recipients) == tuple(f"Match {index:02}" for index in range(50))
    if "group" in types:
        assert all(isinstance(recipient, GroupSharingRecipient) for recipient in result.recipients)


@pytest.mark.parametrize("query", ["", " \t\n", "x" * 201, 123])
def test_query_rejects_blank_oversized_and_nonstring_values(query: object) -> None:
    with pytest.raises(ValidationError):
        SharingRecipientSearchQuery(query=query, scope=SharingScope(recipient_types=BOTH))


@pytest.mark.asyncio
async def test_search_reads_directory_once_without_resolving_results_or_writing_state() -> None:
    ports = transactions()
    users = CountingUsers()
    ports.users = users
    for subject in ("one", "two", "blocked"):
        await users.observe(observation("issuer", subject, "Team Person"))
    await ports.policies.add_grant(AccessGrant(
        node_id=initial_root().id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="blocked"),
        permissions=set(), recursive=False,
    ))
    before_users = users.users.copy()
    before_grants = ports.policies.grants.copy()
    before_owners = ports.policies.owners.copy()
    before_nodes = ports.namespace.nodes.copy()
    result = await SharingService(VerifiedIdentityResolver(), ports, "issuer").search_recipients(
        caller(), initial_root().id, search("team", BOTH),
    )
    assert tuple(recipient.type for recipient in result.recipients) == ("group", "user", "user")
    assert users.searches == [ScopedUserSearch(
        issuer="issuer", query="team", limit=50, excluded_subjects=frozenset({"blocked"}),
    )]
    assert users.users == before_users
    assert ports.policies.grants == before_grants
    assert ports.policies.owners == before_owners
    assert ports.namespace.nodes == before_nodes


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive,permissions", [(True, set()), (False, set()), (False, {"invalid"}), (0, {Permission.READ})])
async def test_protected_user_collision_is_excluded_but_foreign_principal_does_not_block(
    recursive: object, permissions: set[object],
) -> None:
    ports = transactions()
    for subject in ("blocked", "eligible"):
        await ports.users.observe(observation("issuer", subject, "Team Person"))
    await ports.users.observe(observation("foreign", "foreign", "Team Person"))
    await ports.policies.add_grant(AccessGrant.model_construct(
        node_id=initial_root().id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="blocked"),
        permissions=permissions, recursive=recursive,
    ))
    await ports.policies.add_grant(AccessGrant(
        node_id=initial_root().id, principal=Principal(type=PrincipalType.USER, issuer="foreign", id="eligible"),
        permissions={Permission.READ}, recursive=True,
    ))
    result = await SharingService(VerifiedIdentityResolver(), ports, "issuer").search_recipients(
        caller(), initial_root().id, search("team", USER),
    )
    assert len(result.recipients) == 1 and not result.has_more
    assert result.recipients[0].user_id == ports.users.users["issuer", "eligible"].user_id


@pytest.mark.asyncio
async def test_merged_limit_reports_more_even_when_each_source_is_complete(context: SharingContext) -> None:
    directory = DatabaseIdentityDirectory(context.database)
    for index in range(26):
        await directory.observe(observation("issuer", str(index), "Match"))
        await context.groups.register_group_metadata(RegisterGroupMetadata(
            group_id=f"id-{index:02}", label="Match", description="",
        ))
    result = await context.service.search_recipients(caller(), context.node.id, search("match", BOTH))
    assert len(result.recipients) == 50 and result.has_more
    assert tuple(recipient.type for recipient in result.recipients) == ("group",) * 26 + ("user",) * 24
    assert tuple(recipient.group_id for recipient in result.recipients[:26]) == tuple(f"id-{index:02}" for index in range(26))

