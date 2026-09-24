import asyncio
import time
from urllib.parse import parse_qs

import httpx2
import pytest
import pytest_asyncio
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from pydantic import SecretStr

from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    AuthorizationDocument,
    ConnectorOAuth,
    ConnectorOAuthStorage,
    SignInRequired,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import FastMCPDownstreamConnectionFactory
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.probe import FastMCPDownstreamConnection
from umbod.core.connectors.downstream_mcp.models import OAuthCredentialState
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_CREDENTIAL_TABLE,
    ConnectorIdQuery,
    EncryptedCredentialStoreService,
    SaveCredential,
)
from tests.persistence_runtime import create_sqlite_runtime, prepared_sqlite_runtime


@pytest_asyncio.fixture(autouse=True)
async def prepare_oauth_database(tmp_path):
    await prepared_sqlite_runtime(tmp_path / "oauth.sqlite3")


def document(endpoint="https://tools.example/mcp", expired=False):
    return AuthorizationDocument(
        endpoint_url=endpoint,
        client_info=OAuthClientInformationFull(
            client_id="client",
            redirect_uris=["http://127.0.0.1/callback"],
            token_endpoint_auth_method="none",
        ),
        tokens=OAuthToken(
            access_token="old-access",
            refresh_token="old-refresh",
            token_type="Bearer",
            expires_in=3600,
        ),
        expires_at=time.time() + (-10 if expired else 3600),
        metadata=OAuthMetadata(
            issuer="https://auth.example",
            authorization_endpoint="https://auth.example/authorize",
            token_endpoint="https://auth.example/token",
            response_types_supported=["code"],
        ),
        authorization_server="https://auth.example",
    )


def store_at(path):
    return EncryptedCredentialStoreService(
        create_sqlite_runtime(path).database,
        CONNECTOR_CREDENTIAL_TABLE,
        AuthenticatedTextCipher("oauth-test-key"),
    )


async def seed(store, connector_id="one", expired=False):
    value = ConnectorOAuthStorage(document(expired=expired)).export()
    await store.save(
        SaveCredential(
            credential=OAuthCredentialState(connector_id=connector_id, authorization=value)
        )
    )
    return value


@pytest.mark.asyncio
async def test_authorization_is_encrypted_and_survives_new_store(tmp_path):
    path = tmp_path / "oauth.sqlite3"
    original = await seed(store_at(path))
    reopened = store_at(path)
    restored = await reopened.get(ConnectorIdQuery(connector_id="one"))
    assert restored.credential.authorization == original
    assert b"old-access" not in path.read_bytes()
    assert b"old-refresh" not in path.read_bytes()
    assert "old-access" not in restored.credential.model_dump_json()
    assert "old-refresh" not in repr(restored.credential)


@pytest.mark.asyncio
async def test_expired_token_refreshes_once_across_two_clients_and_persists(tmp_path):
    path = tmp_path / "oauth.sqlite3"
    store = store_at(path)
    await seed(store, expired=True)
    refreshes = []

    async def handle(request):
        if str(request.url) == "https://auth.example/token":
            body = parse_qs(request.content.decode())
            assert body["grant_type"] == ["refresh_token"]
            assert body["refresh_token"] == ["old-refresh"]
            refreshes.append(request)
            await asyncio.sleep(0.01)
            return httpx2.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "rotated-refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        assert request.headers["authorization"] == "Bearer new-access"
        return httpx2.Response(200, json={"ok": True})

    async def use():
        oauth = ConnectorOAuth(ConnectorOAuthStorage(document(), "one", store_at(path)))
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle), auth=oauth) as client:
            assert (await client.post("https://tools.example/mcp")).status_code == 200

    await asyncio.gather(use(), use())
    assert len(refreshes) == 1
    saved = await store.get(ConnectorIdQuery(connector_id="one"))
    restored = AuthorizationDocument.model_validate_json(
        saved.credential.authorization.get_secret_value()
    )
    assert restored.tokens.refresh_token == "rotated-refresh"
    assert restored.expires_at > time.time()
    await use()  # Simulates a new runtime provider after restart, no browser.
    assert len(refreshes) == 1


@pytest.mark.asyncio
async def test_stale_refresh_cannot_overwrite_new_sign_in_or_resurrect_deleted_connection(tmp_path):
    store = store_at(tmp_path / "oauth.sqlite3")
    original = await seed(store)
    replacement = SecretStr(document().model_dump_json())
    assert await store.replace_oauth_authorization("one", original, replacement)
    assert not await store.replace_oauth_authorization("one", original, SecretStr("stale"))
    await store.delete(ConnectorIdQuery(connector_id="one"))
    assert not await store.replace_oauth_authorization("one", replacement, original)


@pytest.mark.asyncio
async def test_authorization_is_scoped_to_connector_and_endpoint(tmp_path):
    store = store_at(tmp_path / "oauth.sqlite3")
    await seed(store)
    with pytest.raises(SignInRequired):
        await ConnectorOAuthStorage(document(), "other", store).load()
    with pytest.raises(SignInRequired):
        await ConnectorOAuthStorage(document("https://other.example/mcp"), "one", store).load()


@pytest.mark.asyncio
async def test_runtime_never_starts_browser_authorization():
    oauth = ConnectorOAuth(ConnectorOAuthStorage(document()))
    with pytest.raises(SignInRequired):
        await oauth._perform_authorization()


def test_nested_unauthorized_response_is_not_reported_as_invalid_mcp():
    response = httpx2.Response(401, request=httpx2.Request("POST", "https://tools.example/mcp"))
    error = httpx2.HTTPStatusError("unauthorized", request=response.request, response=response)
    failure = FastMCPDownstreamConnection(
        True, 10, FastMCPDownstreamConnectionFactory(True)
    )._classify_exception(
        ExceptionGroup("transport", [error])
    )
    assert failure.code == "auth_rejected"
