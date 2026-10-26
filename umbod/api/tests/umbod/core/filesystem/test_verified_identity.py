import pytest
from pydantic import ValidationError

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerSnapshot,
    DeclaredIssuer,
    GroupMembership,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.core.filesystem import SYSTEM_ROOT_OWNER, Principal, PrincipalType
from umbod.core.filesystem.authorization import (
    FilesystemIdentityResolver,
    ResolvedIdentity,
    UnresolvedIdentity,
    VerifiedIdentityResolver,
)


def snapshot(subject: str, issuer: str, groups: tuple[str, ...]) -> CallerSnapshot:
    return CallerSnapshot(
        caller=CallerContext(
            authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=subject),
        ),
        groups=GroupMembership(group_ids=groups),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", list(AuthenticationProvenance))
async def test_only_upstream_verified_provenance_resolves(provenance: AuthenticationProvenance) -> None:
    caller = CallerSnapshot(
        caller=CallerContext(
            authentication=provenance,
            subject=UnavailableSubject(kind="unavailable") if provenance == AuthenticationProvenance.UNAVAILABLE else SubjectIdentity(
                issuer=DeclaredIssuer(value="issuer"), subject="alice"
            ),
        ),
        groups=GroupMembership(group_ids=("team",)),
    )
    resolver: FilesystemIdentityResolver = VerifiedIdentityResolver()
    result = await resolver.resolve(caller)
    assert isinstance(result, ResolvedIdentity if provenance == AuthenticationProvenance.UPSTREAM_VERIFIED else UnresolvedIdentity)


@pytest.mark.asyncio
@pytest.mark.parametrize("subject,issuer,groups", [
    ("", "issuer", ()), (" \t", "issuer", ()),
    ("alice", "", ()), ("alice", "\n ", ()),
    ("alice", "issuer", ("team", "")), ("alice", "issuer", (" \t",)),
])
async def test_blank_observation_rejects_entire_snapshot(subject: str, issuer: str, groups: tuple[str, ...]) -> None:
    resolver: FilesystemIdentityResolver = VerifiedIdentityResolver()
    assert isinstance(await resolver.resolve(snapshot(subject, issuer, groups)), UnresolvedIdentity)


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", [
    UnavailableSubject(kind="unavailable"),
    SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice"),
])
async def test_unavailable_subject_or_issuer_is_unresolved(subject: SubjectIdentity | UnavailableSubject) -> None:
    resolver: FilesystemIdentityResolver = VerifiedIdentityResolver()
    caller = CallerSnapshot(caller=CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=subject), groups=GroupMembership(group_ids=()))
    assert isinstance(await resolver.resolve(caller), UnresolvedIdentity)


@pytest.mark.asyncio
async def test_mapping_preserves_exact_namespace_deduplicates_and_observes_each_snapshot() -> None:
    resolver: FilesystemIdentityResolver = VerifiedIdentityResolver()
    first = await resolver.resolve(snapshot(" Alice ", " Issuer ", (" Team ", " Team ")))
    assert first == ResolvedIdentity(
        user=Principal(type=PrincipalType.USER, issuer=" Issuer ", id=" Alice "),
        groups=frozenset({Principal(type=PrincipalType.GROUP, issuer=" Issuer ", id=" Team ")}),
    )
    second = await resolver.resolve(snapshot(" Alice ", " Issuer ", ("other",)))
    assert isinstance(second, ResolvedIdentity)
    assert second.groups == frozenset({Principal(type=PrincipalType.GROUP, issuer=" Issuer ", id="other")})
    assert isinstance(first, ResolvedIdentity)
    assert second.user == first.user
    assert first.groups != second.groups
    different_issuer = await resolver.resolve(snapshot(" Alice ", "issuer", (" Team ",)))
    assert isinstance(different_issuer, ResolvedIdentity)
    assert different_issuer.principals.isdisjoint(first.principals)


@pytest.mark.asyncio
async def test_verified_system_strings_are_only_a_user_identity() -> None:
    resolver: FilesystemIdentityResolver = VerifiedIdentityResolver()
    result = await resolver.resolve(snapshot(SYSTEM_ROOT_OWNER.id, SYSTEM_ROOT_OWNER.issuer, ()))
    assert isinstance(result, ResolvedIdentity)
    assert result.user.type == PrincipalType.USER
    assert SYSTEM_ROOT_OWNER not in result.principals
    with pytest.raises(ValidationError):
        ResolvedIdentity(user=SYSTEM_ROOT_OWNER, groups=frozenset())
    with pytest.raises(ValidationError):
        ResolvedIdentity(user=result.user, groups=frozenset({SYSTEM_ROOT_OWNER}))


def test_snapshot_is_required_frozen_detached_and_claim_free() -> None:
    groups = ["team"]
    membership = GroupMembership(group_ids=groups)
    observed = snapshot("alice", "issuer", membership.group_ids)
    groups.clear()
    assert observed.groups.group_ids == ("team",)
    for field in ("caller", "groups"):
        values = observed.model_dump()
        del values[field]
        with pytest.raises(ValidationError):
            CallerSnapshot.model_validate(values)
    with pytest.raises(ValidationError):
        observed.groups = GroupMembership(group_ids=())
    with pytest.raises(ValidationError):
        observed.caller.subject.subject = "mallory"
    with pytest.raises(ValidationError):
        observed.groups.group_ids = ()
    with pytest.raises(ValidationError):
        CallerSnapshot.model_validate({**observed.model_dump(), "claims": {"admin": True}})
