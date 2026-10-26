import pytest

from umbod.core.callers import (
    AuthenticationProvenance, CallerContext, CallerSnapshot, DeclaredIssuer,
    GroupMembership, SubjectIdentity, UnavailableIssuer, UnavailableSubject,
)
from umbod.core.filesystem import Principal, PrincipalType
from umbod.core.filesystem.authorization import (
    FilesystemIdentityResolver, LocalDevelopmentIdentityResolver,
    ResolvedIdentity, UnresolvedIdentity, VerifiedIdentityResolver,
)

EXPECTED = Principal(type=PrincipalType.USER, issuer="urn:umbod:local", id="test-user")


def local_snapshot(
    provenance: AuthenticationProvenance, issuer: str, subject: str, groups: tuple[str, ...],
) -> CallerSnapshot:
    return CallerSnapshot(
        caller=CallerContext(
            authentication=provenance,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=subject),
        ),
        groups=GroupMembership(group_ids=groups),
    )


@pytest.mark.asyncio
async def test_opt_in_local_identity_preserves_exact_issuer_qualified_groups() -> None:
    resolver: FilesystemIdentityResolver = LocalDevelopmentIdentityResolver(EXPECTED)
    caller = local_snapshot(AuthenticationProvenance.LOCAL_SIMULATION, EXPECTED.issuer, EXPECTED.id, ("admin", " Team ", "admin"))
    assert await resolver.resolve(caller) == ResolvedIdentity(
        user=EXPECTED,
        groups=frozenset({
            Principal(type=PrincipalType.GROUP, issuer=EXPECTED.issuer, id="admin"),
            Principal(type=PrincipalType.GROUP, issuer=EXPECTED.issuer, id=" Team "),
        }),
    )
    strict: FilesystemIdentityResolver = VerifiedIdentityResolver()
    assert isinstance(await strict.resolve(caller), UnresolvedIdentity)


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED, AuthenticationProvenance.LOCAL_SEMANTIC,
    AuthenticationProvenance.LOCAL_TEST,
])
async def test_non_simulated_unverified_provenance_never_resolves(provenance: AuthenticationProvenance) -> None:
    resolver: FilesystemIdentityResolver = LocalDevelopmentIdentityResolver(EXPECTED)
    assert isinstance(await resolver.resolve(local_snapshot(provenance, EXPECTED.issuer, EXPECTED.id, ("admin",))), UnresolvedIdentity)


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,subject,groups", [
    ("other", "test-user", ("admin",)), ("urn:umbod:local", "other", ("admin",)),
    ("urn:umbod:local ", "test-user", ()), ("urn:umbod:local", "test-user ", ()),
    ("urn:umbod:local", "test-user", ("admin", " ")),
])
async def test_local_identity_requires_exact_configured_principal_and_valid_groups(
    issuer: str, subject: str, groups: tuple[str, ...],
) -> None:
    resolver: FilesystemIdentityResolver = LocalDevelopmentIdentityResolver(EXPECTED)
    assert isinstance(await resolver.resolve(local_snapshot(AuthenticationProvenance.LOCAL_SIMULATION, issuer, subject, groups)), UnresolvedIdentity)


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", [
    UnavailableSubject(kind="unavailable"),
    SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="test-user"),
])
async def test_local_identity_rejects_unavailable_identity(subject: SubjectIdentity | UnavailableSubject) -> None:
    resolver: FilesystemIdentityResolver = LocalDevelopmentIdentityResolver(EXPECTED)
    snapshot = CallerSnapshot(
        caller=CallerContext(authentication=AuthenticationProvenance.LOCAL_SIMULATION, subject=subject),
        groups=GroupMembership(group_ids=("admin",)),
    )
    assert isinstance(await resolver.resolve(snapshot), UnresolvedIdentity)


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,subject,groups", [
    ("production-issuer", "alice", ("team",)), ("", "alice", ()),
    ("production-issuer", " ", ()), ("production-issuer", "alice", (" ",)),
])
async def test_real_upstream_callers_keep_strict_resolver_behavior(
    issuer: str, subject: str, groups: tuple[str, ...],
) -> None:
    resolver: FilesystemIdentityResolver = LocalDevelopmentIdentityResolver(EXPECTED)
    strict: FilesystemIdentityResolver = VerifiedIdentityResolver()
    snapshot = local_snapshot(AuthenticationProvenance.UPSTREAM_VERIFIED, issuer, subject, groups)
    assert await resolver.resolve(snapshot) == await strict.resolve(snapshot)
