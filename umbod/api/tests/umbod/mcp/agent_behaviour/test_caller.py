import pytest
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from umbod.config import AppConfig
from umbod.config.defaults import MCP_TEST_BEARER_TOKEN
from umbod.core.agent_behaviour import CallerNotAuthorized
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER, AuthenticationProvenance, DeclaredIssuer, SubjectIdentity, UnavailableIssuer
from umbod.mcp.agent_behaviour.authorization import DiagnosticCallerPolicy
from umbod.mcp.agent_behaviour.caller import CurrentDiagnosticCallerCapture
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider


@pytest.mark.parametrize("allow_local", [True, False])
def test_configured_local_test_provider_uses_reserved_development_issuer_only_when_allowed(allow_local: bool) -> None:
    provider = SingleTestUserOAuthProvider(MCP_TEST_BEARER_TOKEN, "http://localhost")
    capture = CurrentDiagnosticCallerCapture(FastMCP("diagnostic-caller", auth=provider))
    token = AccessToken(token="diagnostic-test-token", client_id="test", scopes=[], claims={"sub": "local-user"})
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        caller = capture.capture()
        assert caller.authentication == AuthenticationProvenance.LOCAL_TEST
        assert caller.subject == SubjectIdentity(issuer=DeclaredIssuer(value=LOCAL_DEVELOPMENT_ISSUER), subject="local-user")
        policy = DiagnosticCallerPolicy(capture, allow_local)
        if allow_local:
            assert policy.require() == caller
        else:
            with pytest.raises(CallerNotAuthorized):
                policy.require()
    finally:
        auth_context_var.reset(reset)


@pytest.mark.asyncio
async def test_default_mcp_diagnostic_reporter_matches_simulated_rest_identity() -> None:
    provider = SingleTestUserOAuthProvider(MCP_TEST_BEARER_TOKEN, "http://localhost")
    capture = CurrentDiagnosticCallerCapture(FastMCP("diagnostic-caller", auth=provider))
    token = await provider.load_access_token(MCP_TEST_BEARER_TOKEN)
    assert token is not None
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        caller = DiagnosticCallerPolicy(capture, True).require()
        assert caller.subject == SubjectIdentity(
            issuer=DeclaredIssuer(value=LOCAL_DEVELOPMENT_ISSUER),
            subject=AppConfig().admin_authentication.simulated_user_id,
        )
    finally:
        auth_context_var.reset(reset)


def test_missing_issuer_is_not_fabricated_for_deployment_authentication() -> None:
    capture = CurrentDiagnosticCallerCapture(FastMCP("diagnostic-caller"))
    token = AccessToken(token="diagnostic-test-token", client_id="test", scopes=[], claims={"sub": "user"})
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        caller = capture.capture()
        assert isinstance(caller.subject, SubjectIdentity)
        assert isinstance(caller.subject.issuer, UnavailableIssuer)
        with pytest.raises(CallerNotAuthorized):
            DiagnosticCallerPolicy(capture, True).require()
    finally:
        auth_context_var.reset(reset)
