from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastmcp import Context, FastMCP
from fastmcp.server.auth import AccessToken, AuthProvider, MultiAuth
from fastmcp.server.auth.providers.google import GoogleProvider
from pydantic import SecretStr
from starlette.testclient import TestClient

from umbod.core.agent_tokens import AgentCredentialVerifier, InvalidAgentCredential, PublicMcpAgentIdentity
from umbod.core.callers import AuthenticationProvenance, CallerContext, UnavailableSubject
from umbod.core.groups import GroupInstanceId
from umbod.mcp.administrator.principal import current_administrator_principal
from umbod.mcp.auth.agent_tokens import (
    create_public_agent_auth,
    effective_oauth_provider,
    is_agent_access_token,
    verified_agent_identity,
)
from umbod.mcp.auth.caller import authentication_provenance_for_token, get_caller_context
from umbod.mcp.logging.audit.identity import McpAuditIdentityAdapter

_AGENT_BEARER = "umbod_agent_v1_test-bearer"
_INVALID_AGENT_BEARER = "umbod_agent_v1_invalid"
_AGENT_ID = "1" * 32
_HUMAN_BEARER = "verified-oauth"
_UNSCOPED_BEARER = "verified-oauth-without-scopes"
_SPOOFED_CLIENT_ID = '["umbod-public-agent","agent-client",null,null]'
_HUMAN_CLAIMS = {
    "sub": "human", "agent_id": _AGENT_ID, "group_id": "internal",
    "iss": "https://accounts.google.com", "groups": ["administrators"],
}
_ACCEPT = {"Accept": "application/json, text/event-stream"}
_CALL = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_caller", "arguments": {}}}


@pytest.fixture
def agent_identity() -> PublicMcpAgentIdentity:
    return PublicMcpAgentIdentity(
        agent_id=_AGENT_ID,
        group_id="internal",
        group_instance_id=GroupInstanceId(UUID(int=2).hex),
        audience="umbod:mcp",
    )


@pytest.fixture
def verifier(agent_identity: PublicMcpAgentIdentity) -> AsyncMock:
    async def verify(token: SecretStr) -> PublicMcpAgentIdentity:
        if token.get_secret_value() == _AGENT_BEARER:
            return agent_identity
        raise InvalidAgentCredential()

    verifier = AsyncMock(spec=AgentCredentialVerifier)
    verifier.verify_for_public_mcp.side_effect = verify
    return verifier


@pytest.fixture
def oauth(monkeypatch: pytest.MonkeyPatch) -> GoogleProvider:
    provider = GoogleProvider(
        client_id="agent-auth-test.apps.googleusercontent.com",
        client_secret="test-only-secret",
        base_url="https://umbod.example.test",
        jwt_signing_key="a" * 32,
        required_scopes=["openid", "email"],
        valid_scopes=["openid", "email", "profile"],
    )

    async def verify(token: str) -> AccessToken:
        assert token not in {_AGENT_BEARER, _INVALID_AGENT_BEARER}, "Reserved bearer reached OAuth"
        return AccessToken(
            token=token,
            client_id=_SPOOFED_CLIENT_ID,
            scopes=provider.required_scopes if token == _HUMAN_BEARER else [],
            claims=_HUMAN_CLAIMS,
            subject="human",
        )

    monkeypatch.setattr(provider, "verify_token", AsyncMock(side_effect=verify))
    return provider


def _server(provider: AuthProvider) -> FastMCP:
    server = FastMCP("public-agent-auth-test", auth=provider)

    @server.tool(name="get_caller")
    def caller() -> CallerContext:
        return get_caller_context(server)

    return server


@pytest.mark.asyncio
async def test_public_auth_preserves_oauth_source_and_rejects_client_id_and_claim_spoofs(
    oauth: GoogleProvider, verifier: AsyncMock,
) -> None:
    auth = create_public_agent_auth(oauth, verifier)
    token = await auth.verify_token(_HUMAN_BEARER)

    assert isinstance(auth, MultiAuth)
    assert token is not None
    assert token.original_client_id == _SPOOFED_CLIENT_ID
    assert token.claims == _HUMAN_CLAIMS
    assert token.scopes == oauth.required_scopes
    assert effective_oauth_provider(auth, token) is oauth
    assert authentication_provenance_for_token(auth, token) is AuthenticationProvenance.UPSTREAM_VERIFIED
    assert not is_agent_access_token(auth, token)
    assert verified_agent_identity(auth, token) is None
    verifier.verify_for_public_mcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_injected_multi_auth_keeps_existing_deployment_provenance(oauth: GoogleProvider) -> None:
    auth = MultiAuth(server=oauth)
    token = await auth.verify_token(_HUMAN_BEARER)

    assert token is not None
    assert authentication_provenance_for_token(auth, token) is AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    assert verified_agent_identity(auth, token) is None


@pytest.mark.asyncio
async def test_public_credential_carries_typed_identity_and_only_required_transport_scopes(
    oauth: GoogleProvider, verifier: AsyncMock, agent_identity: PublicMcpAgentIdentity,
) -> None:
    auth = create_public_agent_auth(oauth, verifier)
    token = await auth.verify_token(_AGENT_BEARER)

    assert token is not None
    assert verified_agent_identity(auth, token) == agent_identity
    assert authentication_provenance_for_token(auth, token) is AuthenticationProvenance.AGENT_CREDENTIAL
    assert effective_oauth_provider(auth, token) is None
    assert token.scopes == oauth.required_scopes != oauth.scopes_supported
    assert token.claims == {}
    assert token.subject is None
    assert _AGENT_BEARER not in repr(token)
    assert _AGENT_BEARER not in token.model_dump_json()
    assert not is_agent_access_token(oauth, token)
    oauth.verify_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_qualified_agent_source_survives_framework_token_serialization_without_identity(
    oauth: GoogleProvider, verifier: AsyncMock,
) -> None:
    auth = create_public_agent_auth(oauth, verifier)
    token = await auth.verify_token(_AGENT_BEARER)
    assert token is not None

    restored = AccessToken.model_validate_json(token.model_dump_json())

    assert is_agent_access_token(auth, restored)
    assert verified_agent_identity(auth, restored) is None
    assert authentication_provenance_for_token(auth, restored) is AuthenticationProvenance.AGENT_CREDENTIAL
    assert effective_oauth_provider(auth, restored) is None


@pytest.mark.asyncio
async def test_invalid_reserved_bearer_never_reaches_oauth(oauth: GoogleProvider, verifier: AsyncMock) -> None:
    auth = create_public_agent_auth(oauth, verifier)

    assert await auth.verify_token(_INVALID_AGENT_BEARER) is None
    oauth.verify_token.assert_not_awaited()
    verifier.verify_for_public_mcp.assert_awaited_once_with(SecretStr(_INVALID_AGENT_BEARER))


@pytest.mark.parametrize("client_id", ["unqualified", '["other","client",null,null]', '["umbod-public-oauth"]'])
def test_unknown_composite_source_does_not_fall_back_to_human_claims(
    oauth: GoogleProvider, verifier: AsyncMock, client_id: str,
) -> None:
    auth = create_public_agent_auth(oauth, verifier)
    token = AccessToken(token=_HUMAN_BEARER, client_id=client_id, scopes=oauth.required_scopes, claims=_HUMAN_CLAIMS)

    assert authentication_provenance_for_token(auth, token) is AuthenticationProvenance.UNAVAILABLE
    assert effective_oauth_provider(auth, token) is None
    assert not is_agent_access_token(auth, token)


def test_public_auth_delegates_oauth_routes_metadata_and_challenge(
    oauth: GoogleProvider, verifier: AsyncMock,
) -> None:
    auth = create_public_agent_auth(oauth, verifier)
    assert [(route.path, route.methods) for route in auth.get_routes("/mcp")] == [
        (route.path, route.methods) for route in oauth.get_routes("/mcp")
    ]
    assert [route.path for route in auth.get_well_known_routes("/mcp")] == [
        route.path for route in oauth.get_well_known_routes("/mcp")
    ]
    paths = [route.path for route in oauth.get_routes("/mcp") if route.path.startswith("/.well-known/")]
    assert paths

    with (
        TestClient(_server(oauth).http_app(stateless_http=True), base_url="https://umbod.example.test") as direct,
        TestClient(_server(auth).http_app(stateless_http=True), base_url="https://umbod.example.test") as composite,
    ):
        for path in paths:
            expected = direct.get(path)
            observed = composite.get(path)
            assert observed.status_code == expected.status_code == 200, path
            assert observed.json() == expected.json()
        expected = direct.post("/mcp", headers=_ACCEPT, json=_CALL)
        observed = composite.post("/mcp", headers=_ACCEPT, json=_CALL)
        assert observed.status_code == expected.status_code == 401
        assert observed.headers["www-authenticate"] == expected.headers["www-authenticate"]


def test_public_http_keeps_oauth_scope_gate_but_admits_verified_agent(
    oauth: GoogleProvider, verifier: AsyncMock,
) -> None:
    auth = create_public_agent_auth(oauth, verifier)

    with TestClient(_server(auth).http_app(stateless_http=True, json_response=True)) as client:
        unscoped = client.post("/mcp", headers={**_ACCEPT, "Authorization": f"Bearer {_UNSCOPED_BEARER}"}, json=_CALL)
        scoped = client.post("/mcp", headers={**_ACCEPT, "Authorization": f"Bearer {_HUMAN_BEARER}"}, json=_CALL)
        agent = client.post("/mcp", headers={**_ACCEPT, "Authorization": f"Bearer {_AGENT_BEARER}"}, json=_CALL)

    assert unscoped.status_code == 403
    assert scoped.status_code == agent.status_code == 200
    assert scoped.json()["result"]["structuredContent"]["authentication"] == AuthenticationProvenance.UPSTREAM_VERIFIED
    assert agent.json()["result"]["structuredContent"] == CallerContext(
        authentication=AuthenticationProvenance.AGENT_CREDENTIAL,
        subject=UnavailableSubject(kind="unavailable"),
    ).model_dump()
    assert _AGENT_BEARER not in agent.text


def test_agent_audit_attributes_agent_id_without_creating_a_human_actor(
    oauth: GoogleProvider, verifier: AsyncMock,
) -> None:
    auth = create_public_agent_auth(oauth, verifier)
    server = FastMCP("agent-audit-test", auth=auth)

    @server.tool(name="get_caller")
    def caller(context: Context) -> dict[str, str | None]:
        actor = McpAuditIdentityAdapter().invocation_actor(context)
        return {"human": actor.authenticated_user_id, "agent": actor.agent_client_id}

    with TestClient(server.http_app(stateless_http=True, json_response=True)) as client:
        response = client.post("/mcp", headers={**_ACCEPT, "Authorization": f"Bearer {_AGENT_BEARER}"}, json=_CALL)

    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"] == {"human": None, "agent": _AGENT_ID}


@pytest.mark.parametrize(("bearer", "groups"), [(_HUMAN_BEARER, ["administrators"]), (_AGENT_BEARER, [])])
def test_mcp_administrator_principal_reads_membership_only_for_human_tokens(
    oauth: GoogleProvider, verifier: AsyncMock, bearer: str, groups: list[str],
) -> None:
    server = FastMCP("administrator-principal-test", auth=create_public_agent_auth(oauth, verifier))

    @server.tool(name="get_caller")
    def caller() -> dict[str, tuple[str, ...]]:
        return {"groups": current_administrator_principal("groups").memberships}

    with TestClient(server.http_app(stateless_http=True, json_response=True)) as client:
        response = client.post("/mcp", headers={**_ACCEPT, "Authorization": f"Bearer {bearer}"}, json=_CALL)

    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"] == {"groups": groups}
