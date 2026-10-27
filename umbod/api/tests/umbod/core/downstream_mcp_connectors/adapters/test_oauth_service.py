"""Behavior exercised without importing or depending on the macOS host."""

from types import SimpleNamespace

import httpx2
import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    AuthorizationDocument,
    ConnectorOAuthStorage,
)
from umbod.core.connectors.downstream_mcp.oauth import service as module
from umbod.core.connectors.downstream_mcp.oauth.ports import OAuthConnection
from umbod.core.connectors.downstream_mcp.oauth.provider import (
    InteractiveConnectorOAuth,
    OAuthFailure,
)
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService

pytestmark = pytest.mark.asyncio


class MemoryHost:
    def __init__(self):
        self.statuses = {}
        self.scopes = "read"
        self.authorized = False
        self.reconnections = 0
        self.saved = ConnectorOAuthStorage(
            AuthorizationDocument(endpoint_url="https://tools.example/mcp"), "", None
        )

    def resolve(self, connector_id):
        if connector_id != "fixture":
            raise KeyError(connector_id)
        return connector_id

    def connection(self, key):
        return OAuthConnection(self.saved.document.endpoint_url, self.scopes)

    def storage(self, key):
        return self.saved

    def callback_url(self, key, *, shared):
        return "http://127.0.0.1/callback" + ("" if shared else "/" + key)

    def set_scopes(self, key, scopes):
        self.scopes = scopes

    def set_authorized(self, key, authorized):
        self.authorized = authorized

    async def delete_authorization(self, key):
        self.saved.document = AuthorizationDocument(
            endpoint_url=self.saved.document.endpoint_url
        )

    async def reconnect(self, key):
        self.reconnections += 1


@pytest.mark.parametrize("failure", [None, "authorization", "discovery"])
async def test_sign_in_distinguishes_authorization_from_discovery(monkeypatch, failure):
    host = MemoryHost()
    oauth = OAuthService(host)

    class Client:
        def __init__(self, transport):
            self.auth = transport.auth

        async def __aenter__(self):
            await self.auth.context.redirect_handler(
                "https://auth.example/authorize?state=expected"
            )
            await self.auth.context.callback_handler()
            if failure == "authorization":
                raise ValueError("access_token=secret")
            await self.auth._handle_token_response(
                httpx2.Response(
                    200,
                    json={
                        "access_token": "secret",
                        "token_type": "Bearer",
                        "scope": "read",
                    },
                )
            )
            return self

        async def list_tools(self):
            if failure == "discovery":
                raise ValueError("access_token=secret")
            return []

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        module, "oauth_client", lambda url, auth: Client(SimpleNamespace(auth=auth))
    )
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
                None: "signed_in",
                "authorization": "failed",
                "discovery": "discovery_failed",
            }[failure]
        )
        assert details["has_authorization"] is (failure != "authorization")
        assert host.authorized is (failure != "authorization")
        assert "secret" not in str(details)
        assert "expected" not in str(details)
        assert not oauth.callbacks
        assert not oauth.expected_states
    finally:
        await oauth.close()


async def test_cancel_preserves_authorization_and_logout_clears_it(monkeypatch):
    host = MemoryHost()
    host.saved.document.tokens = OAuthToken(access_token="saved", token_type="Bearer")
    oauth = OAuthService(host)

    class Client:
        def __init__(self, transport):
            self.auth = transport.auth

        async def __aenter__(self):
            await self.auth.context.redirect_handler(
                "https://auth.example/?state=expected"
            )
            await self.auth.context.callback_handler()

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        module, "oauth_client", lambda url, auth: Client(SimpleNamespace(auth=auth))
    )
    await oauth.begin("fixture", "", None)
    await oauth.cancel("fixture")
    assert host.saved.document.tokens.access_token == "saved"
    assert not oauth.callbacks
    assert oauth.results["fixture"] == "cancelled"
    await oauth.logout("fixture")
    assert host.saved.document.tokens is None
    assert not host.authorized
    assert host.reconnections == 1
    assert not oauth.events
    await oauth.close()


async def test_provider_rejection_is_redacted_and_invalid_client_is_discarded():
    host = MemoryHost()
    host.saved.document.client_info = OAuthClientInformationFull(client_id="rejected")
    host.saved.document.tokens = OAuthToken(access_token="saved", token_type="Bearer")
    auth = InteractiveConnectorOAuth(host.saved)
    with pytest.raises(OAuthFailure, match="registered client") as error:
        await auth._handle_token_response(
            httpx2.Response(
                400,
                json={
                    "error": "invalid_client",
                    "error_description": "secret",
                },
            )
        )
    assert "secret" not in str(error.value)
    assert host.saved.document.client_info is None
    assert host.saved.document.tokens is None


async def test_diagnostics_are_bounded_and_secret_free():
    oauth = OAuthService(MemoryHost())
    for _ in range(30):
        oauth.record("fixture", "metadata", False)
    assert len((await oauth.details("fixture"))["diagnostics"]) == 20
    assert "secret" not in oauth.failure_message(
        ExceptionGroup("secret", [TimeoutError("secret")])
    )
    await oauth.close()
