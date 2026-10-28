from urllib.parse import parse_qs

import httpx2
import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    AuthorizationDocument,
    ConnectorOAuthStorage,
)
from tests.umbod.core.downstream_mcp_connectors.adapters.oauth_fakes import (
    MemoryDiscovery,
    ScriptedSessionFactory,
)
from umbod.core.connectors.downstream_mcp.oauth.ports import OAuthConnection
from umbod.core.connectors.downstream_mcp.oauth.provider import (
    InteractiveConnectorOAuth,
    OAuthFailure,
)
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService

pytestmark = pytest.mark.asyncio


class MemoryHost:
    def __init__(self) -> None:
        self.statuses = {}
        self.scopes = "read"
        self.authorized = False
        self.reconnections = 0
        self.saved = ConnectorOAuthStorage(
            AuthorizationDocument(endpoint_url="https://tools.example/mcp"), "", None
        )

    def resolve(self, connector_id: str) -> str:
        if connector_id != "fixture":
            raise KeyError(connector_id)
        return connector_id

    def connection(self, key: str) -> OAuthConnection:
        return OAuthConnection(self.saved.document.endpoint_url, self.scopes)

    def storage(self, key: str) -> ConnectorOAuthStorage:
        return self.saved

    def callback_url(self, key: str, *, shared: bool) -> str:
        return "http://127.0.0.1/callback" + ("" if shared else "/" + key)

    def set_scopes(self, key: str, scopes: str) -> None:
        self.scopes = scopes

    def set_authorized(self, key: str, authorized: bool) -> None:
        self.authorized = authorized

    async def delete_authorization(self, key: str) -> None:
        self.saved.document = AuthorizationDocument(
            endpoint_url=self.saved.document.endpoint_url
        )

    async def reconnect(self, key: str) -> None:
        self.reconnections += 1


@pytest.mark.parametrize(
    "failure", ["", "authorization", "discovery", "enter_after_tokens"]
)
async def test_sign_in_distinguishes_authorization_from_discovery(failure: str) -> None:
    host = MemoryHost()
    sessions = ScriptedSessionFactory(failure)
    oauth = OAuthService(host, sessions, MemoryDiscovery())
    try:
        result = await oauth.begin("fixture", "", scopes=" read  write ")
        assert result["status"] == "pending"
        assert host.scopes == "read write"
        rejected = await oauth.callback("fixture", {"state": "wrong", "code": "secret"})
        assert rejected.status_code == 400
        assert not oauth.callbacks["fixture"].done()
        accepted = await oauth.callback(None, {"state": "expected", "code": "secret"})
        assert accepted.status_code == 200
        await oauth.tasks["fixture"]
        details = await oauth.details("fixture")
        assert (
            details["status"]
            == {
                "": "signed_in",
                "authorization": "failed",
                "discovery": "discovery_failed",
                "enter_after_tokens": "discovery_failed",
            }[failure]
        )
        assert details["has_authorization"] is (failure != "authorization")
        assert host.authorized is (failure != "authorization")
        assert sessions.sessions[0].disposed
        assert "secret" not in str(details)
        assert "expected" not in str(details)
        assert not oauth.callbacks
        assert not oauth.expected_states
        assert sessions.options[0].requested_scopes == "read write"
        assert sessions.options[0].redirect_uri == "http://127.0.0.1/callback/fixture"
        assert sessions.options[0].metadata_mode == "registration"
    finally:
        await oauth.close()


async def test_cancel_preserves_authorization_and_logout_clears_it() -> None:
    host = MemoryHost()
    await host.saved.set_tokens(OAuthToken(access_token="saved", token_type="Bearer"))
    sessions = ScriptedSessionFactory("")
    oauth = OAuthService(host, sessions, MemoryDiscovery())
    try:
        await oauth.begin("fixture", "", None)
        await oauth.cancel("fixture")
        assert host.saved.document.tokens.access_token == "saved"
        assert sessions.sessions[0].disposed
        assert not oauth.callbacks
        assert oauth.results["fixture"] == "cancelled"
        await oauth.logout("fixture")
        assert host.saved.document.tokens is None
        assert not host.authorized
        assert host.reconnections == 1
        assert not oauth.events
    finally:
        await oauth.close()


@pytest.mark.parametrize("failure", ["", "authorization", "discovery"])
async def test_refresh_uses_a_disposable_session(failure: str) -> None:
    host = MemoryHost()
    await host.saved.set_tokens(
        OAuthToken(
            access_token="saved",
            refresh_token="refresh",
            token_type="Bearer",
        )
    )
    sessions = ScriptedSessionFactory(failure)
    oauth = OAuthService(host, sessions, MemoryDiscovery())
    try:
        if failure:
            with pytest.raises(OAuthFailure, match="Could not refresh"):
                await oauth.refresh("fixture")
            assert host.reconnections == 0
            assert "secret" not in oauth.errors["fixture"]
        else:
            assert await oauth.refresh("fixture") == {"status": "refreshed"}
            assert host.reconnections == 1
        assert sessions.sessions[0].disposed
    finally:
        await oauth.close()


@pytest.mark.parametrize("has_access_token", [False, True])
async def test_refresh_without_refresh_token_never_opens_session(has_access_token: bool) -> None:
    host = MemoryHost()
    if has_access_token:
        await host.saved.set_tokens(OAuthToken(access_token="saved", token_type="Bearer"))
    sessions = ScriptedSessionFactory("")
    oauth = OAuthService(host, sessions, MemoryDiscovery())
    with pytest.raises(OAuthFailure, match="did not issue a refresh token"):
        await oauth.refresh("fixture")
    assert sessions.sessions == []
    await oauth.close()


async def test_discovery_and_hosted_metadata_arguments() -> None:
    host = MemoryHost()
    sessions = ScriptedSessionFactory("")
    discovery = MemoryDiscovery()
    oauth = OAuthService(host, sessions, discovery)
    try:
        preview = await oauth.discover("fixture")
        assert preview["registration"] == "hosted_metadata"
        assert discovery.endpoints == ["https://tools.example/mcp"]
        await oauth.begin("fixture", "", None)
        options = sessions.options[0]
        assert str(options.endpoint) == "https://tools.example/mcp"
        assert options.metadata_mode == "hosted_metadata"
        assert options.redirect_uri == "http://127.0.0.1/callback"
    finally:
        await oauth.close()
    assert sessions.sessions[0].disposed


async def test_provider_rejection_is_redacted_and_invalid_client_is_discarded() -> None:
    host = MemoryHost()
    await host.saved.set_client_info(OAuthClientInformationFull(client_id="rejected"))
    await host.saved.set_tokens(
        OAuthToken(access_token="saved", refresh_token="refresh", token_type="Bearer")
    )
    host.saved.document.metadata = OAuthMetadata(
        issuer="https://auth.example",
        authorization_endpoint="https://auth.example/authorize",
        token_endpoint="https://auth.example/token",
        response_types_supported=["code"],
    )
    auth = InteractiveConnectorOAuth(host.saved, force_refresh=True)
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert str(request.url) == "https://auth.example/token"
        assert parse_qs(request.content.decode())["grant_type"] == ["refresh_token"]
        return httpx2.Response(
            400, json={"error": "invalid_client", "error_description": "secret"}
        )

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handle), auth=auth
    ) as client:
        with pytest.raises(OAuthFailure, match="registered client") as error:
            await client.post(host.saved.document.endpoint_url)
    assert len(requests) == 1
    assert "secret" not in str(error.value)
    assert host.saved.document.client_info is None
    assert host.saved.document.tokens is None


async def test_diagnostics_are_bounded_and_secret_free() -> None:
    oauth = OAuthService(MemoryHost(), ScriptedSessionFactory(""), MemoryDiscovery())
    for _ in range(30):
        oauth.record("fixture", "metadata", False)
    assert len((await oauth.details("fixture"))["diagnostics"]) == 20
    assert "secret" not in oauth.failure_message(
        ExceptionGroup("secret", [TimeoutError("secret")])
    )
    await oauth.close()
