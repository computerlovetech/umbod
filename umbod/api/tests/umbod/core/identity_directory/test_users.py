from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Optional, Protocol

import pytest
import pytest_asyncio
from pydantic import ValidationError

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
)
from umbod.core.identity_directory.models import DirectoryScope, IdentityObservation
from umbod.core.identity_directory.ports import (
    IdentityDirectoryStore,
    ObservedUserDirectory,
)
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.core.identity_directory.user_models import (
    ObservedUserIdentity,
    ObservedUserProfile,
    SubjectUsersLookup,
    ScopedUserSearch,
    UserLookup,
    UserSearchPage,
    UserSearchQuery,
)
from umbod.core.identity_directory.users import (
    ObservedUserNotFound,
    ObservedUserService,
    UserSearchDenied,
)

ISSUER = "https://issuer.test"


class UserDirectory(IdentityDirectoryStore, ObservedUserDirectory, Protocol):
    pass


def caller() -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value=ISSUER), subject="ordinary-user"
        ),
    )


def observation(subject: str, name: str) -> IdentityObservation:
    return IdentityObservation(
        issuer=ISSUER,
        subject=subject,
        claim="groups",
        groups=(),
        name=name,
        email="private@example.test",
        email_verification="verified",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest_asyncio.fixture
async def directory() -> AsyncIterator[UserDirectory]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield DatabaseIdentityDirectory(runtime.database)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["ada", "LOVELACE", "  Ada   Lovelace  ", "love"])
async def test_search_matches_first_last_and_full_names(
    directory: UserDirectory, query: str
) -> None:
    await directory.observe(observation("subject", "Ada  Lovelace"))
    result = await ObservedUserService(directory, ISSUER).search(
        caller(), UserSearchQuery(query=query, limit=50, excluded_subjects=frozenset())
    )
    assert len(result.users) == 1
    assert result.users[0].name == "Ada  Lovelace"
    assert set(result.users[0].model_dump()) == {"user_id", "name"}
    assert not result.has_more


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["private", "secret-subject", "%", "_", "Nobody"])
async def test_search_does_not_match_email_subject_or_wildcards(
    directory: UserDirectory, query: str
) -> None:
    await directory.observe(observation("secret-subject", "Ada Lovelace"))
    result = await ObservedUserService(directory, ISSUER).search(
        caller(), UserSearchQuery(query=query, limit=50, excluded_subjects=frozenset())
    )
    assert result.users == ()


@pytest.mark.asyncio
async def test_search_keeps_duplicate_names_distinct_and_reports_truncation(
    directory: UserDirectory,
) -> None:
    for subject in ("one", "two", "three"):
        await directory.observe(observation(subject, "Ada Lovelace"))
    service = ObservedUserService(directory, ISSUER)
    complete = await service.search(caller(), UserSearchQuery(query="Ada", limit=3, excluded_subjects=frozenset()))
    limited = await service.search(caller(), UserSearchQuery(query="Ada", limit=2, excluded_subjects=frozenset()))
    assert len({user.user_id for user in complete.users}) == 3
    assert not complete.has_more
    assert limited.users == complete.users[:2]
    assert limited.has_more


@pytest.mark.asyncio
async def test_search_and_lookup_are_scoped_to_exact_issuer(
    directory: UserDirectory,
) -> None:
    await directory.observe(
        observation("same", "Ada").model_copy(update={"issuer": "https://other.test"})
    )
    foreign = await directory.search_user_names(
        ScopedUserSearch(issuer="https://other.test", query="Ada", limit=50, excluded_subjects=frozenset())
    )
    assert foreign.users
    service = ObservedUserService(directory, ISSUER)
    assert (
        await service.search(caller(), UserSearchQuery(query="Ada", limit=50, excluded_subjects=frozenset()))
    ).users == ()
    with pytest.raises(ObservedUserNotFound):
        await service.resolve(caller(), foreign.users[0].user_id)


@pytest.mark.asyncio
async def test_resolve_uses_stable_id_and_exact_binding_after_profile_update(
    directory: UserDirectory,
) -> None:
    await directory.observe(observation(" exact-subject ", "Ada Lovelace"))
    service = ObservedUserService(directory, ISSUER)
    user = (
        await service.search(caller(), UserSearchQuery(query="Ada", limit=50, excluded_subjects=frozenset()))
    ).users[0]
    await directory.observe(observation(" exact-subject ", "Updated Name"))
    resolved = await service.resolve(caller(), user.user_id)
    assert resolved == SubjectIdentity(
        issuer=DeclaredIssuer(value=ISSUER), subject=" exact-subject "
    )
    assert (
        await service.search(caller(), UserSearchQuery(query="Updated", limit=50, excluded_subjects=frozenset()))
    ).users[0].user_id == user.user_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id", ["missing", "Ada", "private@example.test", "subject"]
)
async def test_lookup_does_not_resolve_unknown_ids_names_emails_or_subjects(
    directory: UserDirectory, user_id: str
) -> None:
    await directory.observe(observation("subject", "Ada"))
    with pytest.raises(ObservedUserNotFound):
        await ObservedUserService(directory, ISSUER).resolve(caller(), user_id)


@pytest.mark.asyncio
async def test_missing_profile_is_not_searchable_but_identity_can_be_resolved(
    directory: UserDirectory,
) -> None:
    await directory.observe(observation("subject", ""))
    user = (
        await directory.search_users(
            DirectoryScope(
                issuer=ISSUER,
                claim="groups",
                query="",
                limit=50,
            )
        )
    ).users[0]
    assert await directory.find_user_identity(
        UserLookup(issuer=ISSUER, user_id=user.user_id)
    )
    assert (
        await ObservedUserService(directory, ISSUER).search(
            caller(), UserSearchQuery(query="subject", limit=50, excluded_subjects=frozenset())
        )
    ).users == ()


class UnreadableDirectory:
    async def find_subject_users(
        self, lookup: SubjectUsersLookup,
    ) -> tuple[ObservedUserProfile, ...]:
        raise AssertionError("Directory must not be accessed")

    async def search_user_names(self, search: ScopedUserSearch) -> UserSearchPage:
        raise AssertionError("Directory must not be accessed")

    async def find_user_identity(
        self, lookup: UserLookup
    ) -> Optional[ObservedUserIdentity]:
        raise AssertionError("Directory must not be accessed")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authentication",
    [
        AuthenticationProvenance.LOCAL_SIMULATION,
        AuthenticationProvenance.LOCAL_TEST,
        AuthenticationProvenance.LOCAL_SEMANTIC,
        AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    ],
)
async def test_unverified_callers_are_denied_before_directory_access(
    authentication: AuthenticationProvenance,
) -> None:
    service = ObservedUserService(UnreadableDirectory(), ISSUER)
    with pytest.raises(UserSearchDenied):
        await service.search(
            caller().model_copy(update={"authentication": authentication}),
            UserSearchQuery(query="Ada", limit=50, excluded_subjects=frozenset()),
        )
    with pytest.raises(UserSearchDenied):
        await service.resolve(
            caller().model_copy(update={"authentication": authentication}), "unknown"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configured_issuer,verified_issuer", [("", ISSUER), (ISSUER, "https://other.test")]
)
async def test_unconfigured_or_foreign_issuer_is_denied_before_directory_access(
    configured_issuer: str, verified_issuer: str
) -> None:
    service = ObservedUserService(UnreadableDirectory(), configured_issuer)
    with pytest.raises(UserSearchDenied):
        await service.search(
            CallerContext(
                authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
                subject=SubjectIdentity(
                    issuer=DeclaredIssuer(value=verified_issuer),
                    subject="ordinary-user",
                ),
            ),
            UserSearchQuery(query="Ada", limit=50, excluded_subjects=frozenset()),
        )


@pytest.mark.asyncio
async def test_unavailable_issuer_is_denied_before_directory_access() -> None:
    context = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(
            issuer=UnavailableIssuer(kind="unavailable"), subject="ordinary"
        ),
    )
    with pytest.raises(UserSearchDenied):
        await ObservedUserService(UnreadableDirectory(), ISSUER).search(
            context, UserSearchQuery(query="Ada", limit=50, excluded_subjects=frozenset())
        )


@pytest.mark.asyncio
async def test_reverse_profiles_use_exact_issuer_subjects_and_include_nameless_users(
    directory: UserDirectory,
) -> None:
    await directory.observe(observation(" subject ", "Ada"))
    await directory.observe(observation("nameless", ""))
    await directory.observe(observation("unknown", "Hidden"))
    await directory.observe(observation(" subject ", "Foreign").model_copy(update={"issuer": "foreign"}))
    profiles = await ObservedUserService(directory, ISSUER).profiles(
        caller(), frozenset({" subject ", "nameless", "absent"}),
    )
    assert {profile.subject: profile.name for profile in profiles} == {" subject ": "Ada", "nameless": ""}
    assert all(profile.issuer == ISSUER for profile in profiles)
    assert await directory.find_subject_users(SubjectUsersLookup(issuer=ISSUER, subjects=frozenset())) == ()
    assert await directory.find_subject_users(SubjectUsersLookup(issuer=ISSUER, subjects=frozenset({"subject"}))) == ()


@pytest.mark.asyncio
async def test_reverse_profiles_deny_unverified_caller_before_directory_access() -> None:
    with pytest.raises(UserSearchDenied):
        await ObservedUserService(UnreadableDirectory(), ISSUER).profiles(
            caller().model_copy(update={"authentication": AuthenticationProvenance.LOCAL_TEST}),
            frozenset({"subject"}),
        )


@pytest.mark.parametrize("query", ["", "   ", "\t\n", "x" * 201])
def test_search_rejects_blank_or_oversized_query(query: str) -> None:
    with pytest.raises(ValidationError):
        UserSearchQuery(query=query, limit=50, excluded_subjects=frozenset())


@pytest.mark.parametrize("limit", [0, 101, True, "50"])
def test_search_rejects_invalid_limit(limit: object) -> None:
    with pytest.raises(ValidationError):
        UserSearchQuery(query="Ada", limit=limit, excluded_subjects=frozenset())


@pytest.mark.asyncio
async def test_excluded_subjects_are_filtered_before_limit_and_truncation(directory: UserDirectory) -> None:
    for subject in ("blocked-one", "blocked-two", "eligible-one", "eligible-two"):
        await directory.observe(observation(subject, "Ada"))
    result = await ObservedUserService(directory, ISSUER).search(caller(), UserSearchQuery(
        query="Ada", limit=2, excluded_subjects=frozenset({"blocked-one", "blocked-two"}),
    ))
    assert len(result.users) == 2 and not result.has_more
    identities = [await directory.find_user_identity(UserLookup(issuer=ISSUER, user_id=user.user_id)) for user in result.users]
    assert {identity.subject for identity in identities if identity is not None} == {"eligible-one", "eligible-two"}
    limited = await ObservedUserService(directory, ISSUER).search(caller(), UserSearchQuery(
        query="Ada", limit=1, excluded_subjects=frozenset({"blocked-one", "blocked-two"}),
    ))
    assert limited.users == result.users[:1] and limited.has_more


def test_search_requires_explicit_neutral_exclusions() -> None:
    with pytest.raises(ValidationError):
        UserSearchQuery.model_validate({"query": "Ada", "limit": 50})

