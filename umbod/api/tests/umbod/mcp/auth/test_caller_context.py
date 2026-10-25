import asyncio
from contextvars import ContextVar
from typing import Optional

import pytest
from fastmcp.server.auth import AccessToken

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerContextProvider,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.mcp.auth.caller import McpCallerContextProvider
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.caller import RestCallerContextProvider


def test_rest_and_mcp_observe_the_same_subject_identity() -> None:
    claims: dict[str, object] = {"iss": "https://issuer.example/", "sub": " Alice "}
    rest: CallerContextProvider = RestCallerContextProvider(
        JwtClaims(claims=claims), AuthenticationProvenance.UPSTREAM_VERIFIED
    )
    mcp: CallerContextProvider = McpCallerContextProvider(
        lambda: AccessToken(token="secret", client_id="client", scopes=[], claims=claims),
        AuthenticationProvenance.UPSTREAM_VERIFIED,
    )
    assert rest.get_context() == mcp.get_context()
    assert mcp.get_context().subject == SubjectIdentity(
        issuer=DeclaredIssuer(value="https://issuer.example/"), subject=" Alice "
    )


def test_mcp_does_not_infer_provenance_from_claims() -> None:
    provider: CallerContextProvider = McpCallerContextProvider(
        lambda: AccessToken(token="secret", client_id="client", scopes=[], claims={
            "sub": "alice", "authentication": "upstream_verified", "token": "nested-secret"
        }),
        AuthenticationProvenance.LOCAL_TEST,
    )
    context = provider.get_context()
    assert context.authentication == AuthenticationProvenance.LOCAL_TEST
    assert context.subject == SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice")
    assert "secret" not in context.model_dump_json()


@pytest.mark.parametrize("claims", [{}, {"sub": None}, {"sub": 123}])
def test_authenticated_mcp_without_a_string_subject_remains_explicit(claims: dict[str, object]) -> None:
    provider: CallerContextProvider = McpCallerContextProvider(
        lambda: AccessToken(token="secret", client_id="client", scopes=[], claims=claims),
        AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    )
    assert provider.get_context() == CallerContext(
        authentication=AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
        subject=UnavailableSubject(kind="unavailable"),
    )


def test_missing_mcp_authentication_has_no_subject() -> None:
    provider: CallerContextProvider = McpCallerContextProvider(
        lambda: None, AuthenticationProvenance.UPSTREAM_VERIFIED
    )
    assert provider.get_context() == CallerContext(
        authentication=AuthenticationProvenance.UNAVAILABLE,
        subject=UnavailableSubject(kind="unavailable"),
    )


def test_mcp_context_is_a_detached_observation_and_not_cached() -> None:
    access_token = AccessToken(token="secret", client_id="client", scopes=[], claims={"sub": "alice"})
    provider: CallerContextProvider = McpCallerContextProvider(
        lambda: access_token, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    )
    first = provider.get_context()
    access_token.claims["sub"] = "bob"
    assert isinstance(first.subject, SubjectIdentity)
    assert first.subject.subject == "alice"
    assert provider.get_context().subject == SubjectIdentity(
        issuer=UnavailableIssuer(kind="unavailable"), subject="bob"
    )


@pytest.mark.asyncio
async def test_one_mcp_provider_isolates_concurrent_callers() -> None:
    current: ContextVar[Optional[AccessToken]] = ContextVar("caller-context-test")
    provider: CallerContextProvider = McpCallerContextProvider(
        lambda: current.get(None), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    )

    async def observe(subject: str) -> CallerContext:
        reset = current.set(AccessToken(token=subject, client_id="client", scopes=[], claims={"sub": subject}))
        try:
            await asyncio.sleep(0)
            return provider.get_context()
        finally:
            current.reset(reset)

    contexts = await asyncio.gather(observe("alice"), observe("bob"))
    assert [context.subject for context in contexts] == [
        SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice"),
        SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="bob"),
    ]
    assert isinstance(provider.get_context().subject, UnavailableSubject)
