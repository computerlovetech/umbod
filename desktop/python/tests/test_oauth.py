import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx2
import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from starlette.requests import Request
from test_runtime import MemoryVault
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    ConnectorOAuth,
    SignInRequired,
)
from umbod.core.connectors.downstream_mcp.oauth.provider import (
    CLIENT_METADATA_URL,
    InteractiveConnectorOAuth,
    OAuthFailure,
    RuntimeOAuth,
)
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService

from umbod_desktop.backend_integration.oauth import (
    DesktopOAuthHost,
    KeychainOAuthStorage,
    callback_transport,
)
from umbod_desktop.contracts import UpstreamInput


def desktop_oauth(upstreams: Any) -> OAuthService:
    return OAuthService(DesktopOAuthHost(upstreams))


async def test_fresh_authorization_keeps_saved_tokens_and_hosted_identity():

    vault = MemoryVault()
    storage = KeychainOAuthStorage(vault, "fixture", "https://tools.example/mcp")
    storage.document.client_info = OAuthClientInformationFull(client_id=CLIENT_METADATA_URL)
    storage.document.tokens = OAuthToken(access_token="existing", token_type="Bearer", scope="read write")
    await storage.save()
    auth = InteractiveConnectorOAuth(storage, requested_scope="read", force_authorization=True)
    await auth._initialize()
    assert auth.context.current_tokens is None
    assert auth.context.client_metadata_url == CLIENT_METADATA_URL
    await storage.load()
    assert storage.document.tokens.access_token == "existing"
    runtime = RuntimeOAuth(storage, lambda: None)
    await runtime._initialize()
    assert runtime.context.current_tokens.access_token == "existing"
    assert runtime.context.client_metadata_url == CLIENT_METADATA_URL
    await auth._handle_token_response(httpx2.Response(200, json={
        "access_token": "replacement", "token_type": "Bearer", "scope": "read",
    }))
    await auth._initialize()
    assert auth.context.current_tokens.access_token == "replacement"
    assert auth.token_received


async def test_explicit_scopes_limit_browser_request_after_discovery() -> None:
    from urllib.parse import urlsplit

    from mcp.client.auth import AuthorizationCodeResult

    from umbod_desktop.backend_integration.models import DesktopServer

    query = {}

    async def redirect(url):
        query.update(parse_qs(urlsplit(url).query))

    async def callback():
        return AuthorizationCodeResult(code="fixture", state=query["state"][0])

    auth = InteractiveConnectorOAuth(
        KeychainOAuthStorage(MemoryVault(), "scope", "https://tools.example/mcp"),
        requested_scope="channels:read search:read.public",
        redirect_handler=redirect, callback_handler=callback,
    )
    auth.context.client_info = OAuthClientInformationFull(client_id="fixture")
    auth.context.client_metadata.scope = "channels:read chat:write files:write"
    await auth._perform_authorization()
    assert query["scope"] == ["channels:read search:read.public"]
    assert query["code_challenge_method"] == ["S256"]
    saved = DesktopServer.model_validate({
        "name": "Fixture", "transport": "http", "url": "https://tools.example/mcp",
        "oauth": True, "oauth_scopes": query["scope"][0],
    }).model_dump()
    assert DesktopServer.model_validate(saved).oauth_scopes == query["scope"][0]


async def test_retry_reuses_registered_callback_and_migrates_old_uri(monkeypatch):
    from umbod.core.connectors.downstream_mcp.oauth import service as module

    vault = MemoryVault()
    storage = KeychainOAuthStorage(vault, "fixture", "https://tools.example/mcp")
    storage.document.client_info = OAuthClientInformationFull(
        client_id="old", redirect_uris=["http://127.0.0.1:8000/desktop/oauth/callback/old"]
    )
    await storage.save()
    registrations = []
    redirects = []

    class Client:
        def __init__(self, auth):
            self.auth = auth

        async def __aenter__(self):
            info = self.auth.storage.document.client_info
            uri = str(self.auth.context.client_metadata.redirect_uris[0])
            redirects.append(uri)
            if info is None:
                registrations.append(uri)
                await self.auth.storage.set_client_info(
                    OAuthClientInformationFull(client_id="new", redirect_uris=[uri])
                )
            await self.auth.context.redirect_handler("https://tools.example/auth?state=fresh")
            await self.auth.context.callback_handler()
            return self

        async def list_tools(self):
            return []

        async def __aexit__(self, *_):
            pass

    async def start(*_):
        pass

    upstreams = SimpleNamespace(
        vault=vault, origin="http://127.0.0.1:8000", start=start,
        state=SimpleNamespace(data={"servers": {"fixture": {
            "transport": "http", "url": "https://tools.example/mcp"
        }}}, save=lambda: None),
    )
    monkeypatch.setattr(module, "oauth_client", lambda url, auth: Client(auth))
    oauth = desktop_oauth(upstreams)
    for _ in range(2):
        await oauth.begin("fixture", "", None)
        oauth.callbacks["fixture"].set_result(None)
        await oauth.tasks["fixture"]
        assert oauth.results["fixture"] == "signed_in"
    assert redirects == ["http://127.0.0.1:8000/desktop/oauth/callback/fixture"] * 2
    assert registrations == redirects[:1]
    await oauth.begin("fixture", "", None)
    await oauth.cancel("fixture")
    assert oauth.results["fixture"] == "cancelled"
    assert not oauth.callbacks
    assert not oauth.expected_states
    await storage.load()
    assert storage.document.client_info.client_id == "new"
    details = await oauth.details("fixture")
    assert details["stage"] == "cancelled"
    assert "fresh" not in str(details["diagnostics"])


def test_failure_messages_do_not_expose_provider_secrets():
    from mcp.client.auth.exceptions import OAuthTokenError

    error = ExceptionGroup("secret", [OAuthTokenError("access_token=secret")])
    message = OAuthService.failure_message(error)
    assert "token exchange" in message
    assert "secret" not in message


async def test_refresh_failure_is_actionable_and_redacted(monkeypatch):
    from mcp.client.auth.exceptions import OAuthTokenError


    oauth = desktop_oauth(SimpleNamespace())

    async def fail(_):
        raise ExceptionGroup("secret", [OAuthTokenError("refresh_token=secret")])

    monkeypatch.setattr(oauth, "_refresh", fail)
    with pytest.raises(OAuthFailure, match="Sign in with browser") as failure:
        await oauth.refresh("fixture")
    assert "secret" not in str(failure.value)
    assert oauth.events["fixture"][-1]["result"] == "failed"


async def test_missing_refresh_token_is_reported_without_expiring_access():

    vault = MemoryVault()
    storage = KeychainOAuthStorage(vault, "fixture", "https://tools.example/mcp")
    storage.document.tokens = OAuthToken(access_token="fixture-secret", token_type="Bearer")
    storage.document.expires_at = time.time() + 3600
    await storage.save()
    oauth = desktop_oauth(SimpleNamespace(vault=vault, origin="http://127.0.0.1:8000", state=SimpleNamespace(data={
        "servers": {"fixture": {"url": "https://tools.example/mcp"}},
    })))
    details = await oauth.details("fixture")
    assert details["has_authorization"]
    assert not details["has_refresh_token"]
    assert "fixture-secret" not in str(details)
    with pytest.raises(OAuthFailure, match="did not issue a refresh token"):
        await oauth.refresh("fixture")
    await storage.load()
    assert storage.document.expires_at > time.time()


async def test_rejected_refresh_does_not_expire_a_valid_saved_token():

    storage = KeychainOAuthStorage(MemoryVault(), "fixture", "https://tools.example/mcp")
    storage.document.tokens = OAuthToken(access_token="fixture-secret", token_type="Bearer", refresh_token="fixture-refresh")
    storage.document.expires_at = time.time() + 3600
    await storage.save()
    auth = InteractiveConnectorOAuth(storage, force_refresh=True)
    await auth._initialize()
    assert auth.context.token_expiry_time < time.time()
    with pytest.raises(OAuthFailure, match="refresh token expired") as failure:
        await auth._handle_refresh_response(httpx2.Response(400, json={"error": "invalid_grant", "error_description": "secret"}))
    assert "secret" not in str(failure.value)
    await storage.load()
    assert storage.document.expires_at > time.time()


async def test_exact_issuer_survives_discovery_and_keychain_round_trip():
    from mcp.client.auth.utils import validate_authorization_response_iss


    storage = KeychainOAuthStorage(MemoryVault(), "issuer", "https://tools.example/mcp")
    auth = InteractiveConnectorOAuth(storage)
    assert auth.context.client_metadata.token_endpoint_auth_method == "none"
    await auth._handle_oauth_metadata_response(httpx2.Response(200, json={
        "issuer": "https://tools.example",
        "authorization_endpoint": "https://tools.example/authorize",
        "token_endpoint": "https://tools.example/token",
        "response_types_supported": ["code"],
        "authorization_response_iss_parameter_supported": True,
    }))
    validate_authorization_response_iss("https://tools.example", auth.context.oauth_metadata)
    await storage.load()
    validate_authorization_response_iss("https://tools.example", storage.document.metadata)
    with pytest.raises(Exception, match="mismatch"):
        validate_authorization_response_iss("https://other.example", storage.document.metadata)


@pytest.mark.parametrize("provider_error", ["invalid_client", {"token": "secret"}])
async def test_token_failure_exposes_only_safe_category(provider_error):

    auth = InteractiveConnectorOAuth(
        KeychainOAuthStorage(MemoryVault(), "failure", "https://tools.example/mcp")
    )
    with pytest.raises(OAuthFailure) as caught:
        await auth._handle_token_response(httpx2.Response(400, json={
            "error": provider_error, "error_description": "access_token=secret",
        }))
    assert "HTTP 400" in str(caught.value)
    assert "secret" not in str(caught.value)


async def test_keychain_refresh_is_serialized_persistent_and_cannot_resurrect_logout():
    vault = MemoryVault()
    storage = KeychainOAuthStorage(vault, "fixture", "https://tools.example/mcp")
    storage.document.client_info = OAuthClientInformationFull(client_id="fixture")
    storage.document.tokens = OAuthToken(
        access_token="expired", refresh_token="refresh", token_type="Bearer"
    )
    storage.document.expires_at = time.time() - 1
    storage.document.metadata = OAuthMetadata(
        issuer="https://auth.example",
        authorization_endpoint="https://auth.example/authorize",
        token_endpoint="https://auth.example/token",
        response_types_supported=["code"],
    )
    storage.document.authorization_server = "https://auth.example"
    await storage.save()
    refreshes = []

    async def handle(request):
        if str(request.url) == "https://auth.example/token":
            assert parse_qs(request.content.decode())["grant_type"] == ["refresh_token"]
            refreshes.append(request)
            await asyncio.sleep(0.01)
            return httpx2.Response(
                200,
                json={
                    "access_token": "fresh",
                    "refresh_token": "rotated",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        assert request.headers["authorization"] == "Bearer fresh"
        return httpx2.Response(200, json={})

    async def use():
        auth = ConnectorOAuth(
            KeychainOAuthStorage(vault, "fixture", "https://tools.example/mcp")
        )
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handle), auth=auth
        ) as client:
            assert (await client.post("https://tools.example/mcp")).status_code == 200

    await asyncio.gather(use(), use())
    await use()
    assert len(refreshes) == 1
    await storage.load()
    assert storage.document.tokens.refresh_token == "rotated"
    vault.delete(storage.reference)
    with pytest.raises(SignInRequired):
        await storage.save()
    assert vault.get(storage.reference) is None


async def test_wrong_callback_state_does_not_consume_pending_sign_in():
    oauth = desktop_oauth(SimpleNamespace())
    future = asyncio.get_running_loop().create_future()
    oauth.callbacks["nonce"] = future
    oauth.expected_states["nonce"] = "expected"

    def request(state):
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/desktop/oauth/callback/nonce",
                "path_params": {"nonce": "nonce"},
                "query_string": f"code=fixture&state={state}".encode(),
                "headers": [],
            }
        )

    assert (await callback_transport(oauth)(request("wrong"))).status_code == 400
    assert not future.done()
    assert (await callback_transport(oauth)(request("expected"))).status_code == 200
    assert future.result().code == "fixture"
    assert (await callback_transport(oauth)(request("expected"))).status_code == 400


async def test_declined_browser_consent_finishes_pending_callback():
    oauth = desktop_oauth(SimpleNamespace())
    future = asyncio.get_running_loop().create_future()
    oauth.callbacks["nonce"] = future
    oauth.expected_states["nonce"] = "expected"
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/desktop/oauth/callback/nonce",
            "path_params": {"nonce": "nonce"},
            "query_string": b"error=access_denied&state=expected",
            "headers": [],
        }
    )
    assert (await callback_transport(oauth)(request)).status_code == 200
    with pytest.raises(ValueError, match="declined"):
        await future


async def test_runtime_reauthentication_is_reported_and_persisted(tmp_path: Path) -> None:
    from umbod.core.connectors.downstream_mcp.oauth.provider import RuntimeOAuth

    from umbod_desktop.backend_integration.transports import DesktopUpstreams
    from umbod_desktop.storage import DesktopState

    vault = MemoryVault()
    upstreams = DesktopUpstreams(
        DesktopState(tmp_path), vault, "fixture", "http://127.0.0.1:8000"
    )
    storage = KeychainOAuthStorage(vault, "fixture", "https://tools.example/mcp")
    storage.document.client_info = OAuthClientInformationFull(client_id="fixture")
    storage.document.metadata = OAuthMetadata(
        issuer="https://tools.example",
        authorization_endpoint="https://tools.example/authorize",
        token_endpoint="https://tools.example/token",
        response_types_supported=["code"],
    )
    storage.document.authorization_server = "https://tools.example"
    await storage.save()

    async def handle(request):
        return httpx2.Response(404 if ".well-known" in str(request.url) else 401)

    auth = RuntimeOAuth(storage, lambda: upstreams.set_authentication_status("fixture", "sign_in_required"))
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handle), auth=auth
    ) as client:
        with pytest.raises(SignInRequired):
            await client.post("https://tools.example/mcp")
    assert desktop_oauth(upstreams).results["fixture"] == "sign_in_required"
    restored = DesktopUpstreams(
        DesktopState(tmp_path), vault, "fixture", "http://127.0.0.1:8000"
    )
    assert restored.authentication_status["fixture"] == "sign_in_required"


async def test_http_challenge_and_success_update_connection_status(tmp_path: Path) -> None:
    import socket

    import uvicorn
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp.server.auth import AccessToken, TokenVerifier

    from umbod_desktop.backend_integration.transports import DesktopUpstreams
    from umbod_desktop.storage import DesktopState

    class FixtureVerifier(TokenVerifier):
        async def verify_token(self, token):
            if token == "fixture-token":
                return AccessToken(token=token, client_id="fixture", scopes=[])
            return None

    fixture = FastMCP("protected", auth=FixtureVerifier())

    @fixture.tool
    def echo() -> str:
        return "fixture"

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        url = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
        server = uvicorn.Server(
            uvicorn.Config(fixture.http_app(path="/mcp"), log_level="error")
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))
        upstreams = DesktopUpstreams(
            DesktopState(tmp_path), MemoryVault(), "fixture", "http://127.0.0.1:8000"
        )
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    await asyncio.sleep(0.01)
                prepared = await upstreams.prepare(UpstreamInput({"name": "Protected", "transport": "http", "url": url}))
                key = prepared.host_id
                proxy = upstreams.apps[key]

                def transport():
                    return StreamableHttpTransport(
                        "http://127.0.0.1/mcp",
                        headers={"Authorization": "Bearer fixture"},
                        httpx_client_factory=lambda **kw: httpx2.AsyncClient(
                            transport=httpx2.ASGITransport(app=proxy), **kw
                        ),
                    )

                with pytest.raises(Exception):
                    async with Client(transport()) as client:
                        await client.list_tools()
                assert upstreams.authentication_status[key] == "sign_in_required"
                upstreams.vault.set("upstream:fixture", "Bearer fixture-token")
                await upstreams.prepare(UpstreamInput({
                        "host_id": key,
                        "name": "Protected",
                        "transport": "http",
                        "url": url,
                        "headers": {"Authorization": "upstream:fixture"},
                    }))
                proxy = upstreams.apps[key]
                async with Client(transport()) as client:
                    assert [tool.name for tool in await client.list_tools()] == ["echo"]
                assert upstreams.authentication_status[key] == "signed_out"
        finally:
            await upstreams.close()
            server.should_exit = True
            await task


async def test_shared_callback_routes_only_matching_state():
    oauth = desktop_oauth(SimpleNamespace())
    first = asyncio.get_running_loop().create_future()
    second = asyncio.get_running_loop().create_future()
    oauth.callbacks.update(first=first, second=second)
    oauth.expected_states.update(first="state-one", second="state-two")
    request = Request({
        "type": "http", "method": "GET", "path": "/desktop/oauth/callback",
        "path_params": {}, "query_string": b"code=fixture&state=state-two", "headers": [],
    })
    assert (await callback_transport(oauth)(request)).status_code == 200
    assert not first.done()
    assert second.result().code == "fixture"
    assert (await callback_transport(oauth)(request)).status_code == 400
