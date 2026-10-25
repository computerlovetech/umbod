import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.mcp.auth import caller
from umbod.mcp.auth.caller import caller_context_from_access_token, get_caller_context
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.caller import caller_context_from_claims


def test_rest_and_mcp_observe_the_same_subject_identity() -> None:
    claims: dict[str, object] = {"iss": "https://issuer.example/", "sub": " Alice "}
    rest = caller_context_from_claims(
        JwtClaims(claims=claims), AuthenticationProvenance.UPSTREAM_VERIFIED
    )
    mcp = caller_context_from_access_token(
        AccessToken(token="secret", client_id="client", scopes=[], claims=claims),
        AuthenticationProvenance.UPSTREAM_VERIFIED,
    )
    assert rest == mcp
    assert mcp.subject == SubjectIdentity(
        issuer=DeclaredIssuer(value="https://issuer.example/"), subject=" Alice "
    )


def test_mcp_does_not_infer_provenance_from_claims() -> None:
    context = caller_context_from_access_token(
        AccessToken(token="secret", client_id="client", scopes=[], claims={
            "sub": "alice", "authentication": "upstream_verified", "token": "nested-secret"
        }),
        AuthenticationProvenance.LOCAL_TEST,
    )
    assert context.authentication == AuthenticationProvenance.LOCAL_TEST
    assert context.subject == SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice")
    assert "secret" not in context.model_dump_json()


@pytest.mark.parametrize("claims", [{}, {"sub": None}, {"sub": 123}])
def test_authenticated_mcp_without_a_string_subject_remains_explicit(claims: dict[str, object]) -> None:
    context = caller_context_from_access_token(
        AccessToken(token="secret", client_id="client", scopes=[], claims=claims),
        AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    )
    assert context == CallerContext(
        authentication=AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
        subject=UnavailableSubject(kind="unavailable"),
    )


def test_missing_mcp_authentication_has_no_subject() -> None:
    context = caller_context_from_access_token(None, AuthenticationProvenance.UPSTREAM_VERIFIED)
    assert context == CallerContext(
        authentication=AuthenticationProvenance.UNAVAILABLE,
        subject=UnavailableSubject(kind="unavailable"),
    )


def test_mcp_context_is_a_detached_observation_and_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    access_token = AccessToken(token="secret", client_id="client", scopes=[], claims={"sub": "alice"})
    reader = Mock(return_value=access_token)
    monkeypatch.setattr(caller, "get_access_token", reader)
    server = FastMCP("test")
    first = get_caller_context(server)
    access_token.claims["sub"] = "bob"
    assert isinstance(first.subject, SubjectIdentity)
    assert first.subject.subject == "alice"
    assert get_caller_context(server).subject == SubjectIdentity(
        issuer=UnavailableIssuer(kind="unavailable"), subject="bob"
    )
    assert reader.call_count == 2


@pytest.mark.parametrize("provider,expected", [
    (None, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    (object(), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    (object.__new__(SingleTestUserOAuthProvider), AuthenticationProvenance.LOCAL_TEST),
])
def test_current_dependency_uses_actual_server_authentication(
    provider: object, expected: AuthenticationProvenance, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = AccessToken(token="secret", client_id="client", scopes=[], claims={"sub": "alice"})
    reader = Mock(return_value=token)
    monkeypatch.setattr(caller, "get_access_token", reader)
    context = get_caller_context(SimpleNamespace(auth=provider))
    assert context.authentication == expected
    reader.assert_called_once_with()


@pytest.mark.asyncio
async def test_current_mcp_dependency_isolates_concurrent_callers() -> None:
    server = FastMCP("test")

    async def observe(subject: str) -> CallerContext:
        token = AccessToken(token=subject, client_id="client", scopes=[], claims={"sub": subject})
        reset = auth_context_var.set(AuthenticatedUser(token))
        try:
            await asyncio.sleep(0)
            return get_caller_context(server)
        finally:
            auth_context_var.reset(reset)

    contexts = await asyncio.gather(observe("alice"), observe("bob"))
    assert [context.subject for context in contexts] == [
        SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice"),
        SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="bob"),
    ]
    assert isinstance(get_caller_context(server).subject, UnavailableSubject)
