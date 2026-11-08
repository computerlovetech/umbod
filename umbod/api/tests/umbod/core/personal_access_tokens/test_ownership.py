from typing import cast

import pytest

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.core.personal_access_tokens import (
    IssuePersonalAccessToken,
    PersonalAccessTokenPolicy,
    PersonalAccessTokenService,
    UntrustedPersonalAccessTokenCaller,
)
from umbod.core.personal_access_tokens.factory import SecurePersonalAccessTokenGenerator
from umbod.core.personal_access_tokens.ownership import (
    LocalDevelopmentPersonalAccessTokenOwnerResolver,
    VerifiedPersonalAccessTokenOwnerResolver,
)
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore

from .conftest import MutableClock
from .test_service import validation


def simulated_caller(subject: str = "alice", issuer: str = "urn:umbod:local") -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.LOCAL_SIMULATION,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=subject),
    )


@pytest.mark.parametrize(
    "caller",
    [
        simulated_caller(issuer="forged"),
        simulated_caller(issuer="urn:umbod:local "),
        simulated_caller(subject="bob"),
        simulated_caller(subject="Alice"),
        simulated_caller(subject="alice "),
        CallerContext(
            authentication=AuthenticationProvenance.LOCAL_SIMULATION,
            subject=SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice"),
        ),
        CallerContext(
            authentication=AuthenticationProvenance.LOCAL_SIMULATION,
            subject=UnavailableSubject(kind="unavailable"),
        ),
        *[
            CallerContext(authentication=authentication, subject=simulated_caller().subject)
            for authentication in (
                AuthenticationProvenance.LOCAL_SEMANTIC,
                AuthenticationProvenance.LOCAL_TEST,
                AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
            )
        ],
        CallerContext(
            authentication=AuthenticationProvenance.UNAVAILABLE,
            subject=UnavailableSubject(kind="unavailable"),
        ),
        cast(CallerContext, None),
    ],
)
def test_local_resolution_rejects_untrusted_identity(caller: CallerContext) -> None:
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        LocalDevelopmentPersonalAccessTokenOwnerResolver("alice").resolve(caller)


def test_verified_resolver_rejects_exact_local_identity() -> None:
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        VerifiedPersonalAccessTokenOwnerResolver().resolve(simulated_caller())


@pytest.mark.parametrize("subject", ["", " "])
def test_local_resolver_requires_configured_subject(subject: str) -> None:
    with pytest.raises(ValueError, match="configured"):
        LocalDevelopmentPersonalAccessTokenOwnerResolver(subject)


def test_local_resolver_delegates_genuinely_verified_identity(caller: CallerContext) -> None:
    assert LocalDevelopmentPersonalAccessTokenOwnerResolver("alice").resolve(caller) == (
        VerifiedPersonalAccessTokenOwnerResolver().resolve(caller)
    )
    assert caller.authentication == AuthenticationProvenance.UPSTREAM_VERIFIED


@pytest.mark.asyncio
async def test_explicit_local_service_preserves_owner_isolation_and_default_validation(
    store: DatabasePersonalAccessTokenStore,
    clock: MutableClock,
    request_token: IssuePersonalAccessToken,
    service: PersonalAccessTokenService,
    caller: CallerContext,
) -> None:
    local = PersonalAccessTokenService(
        store=store,
        clock=clock,
        generator=SecurePersonalAccessTokenGenerator(),
        policy=PersonalAccessTokenPolicy(allowed_scopes=("telemetry:read",)),
        owner_resolver=LocalDevelopmentPersonalAccessTokenOwnerResolver("alice"),
    )
    simulated = simulated_caller()
    issued = await local.issue(simulated, request_token)
    assert issued.metadata.owner.issuer == "urn:umbod:local"
    assert issued.metadata.owner.subject == "alice"
    assert simulated.authentication == AuthenticationProvenance.LOCAL_SIMULATION
    assert await local.list_tokens(simulated) == (issued.metadata,)
    assert await service.list_tokens(caller) == ()
    assert not await service.revoke(caller, issued.metadata.token_id)
    assert await service.validate(validation(issued.token)) == issued.metadata
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.issue(simulated, request_token)
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.list_tokens(simulated)
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await service.revoke(simulated, issued.metadata.token_id)
    with pytest.raises(UntrustedPersonalAccessTokenCaller):
        await local.revoke(simulated_caller("bob"), issued.metadata.token_id)
    assert await local.list_tokens(simulated) == (issued.metadata,)
    assert await local.revoke(simulated, issued.metadata.token_id)
