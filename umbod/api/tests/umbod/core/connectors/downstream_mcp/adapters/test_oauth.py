import asyncio
import time
from collections.abc import AsyncIterator
from typing import cast
from urllib.parse import parse_qs

import httpx2
import pytest
import pytest_asyncio
from fastmcp import Client
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from pydantic import SecretStr

from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage import AuthorizationDocument
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage_adapters import (
    DetachedConnectorOAuthStorage,
    PersistedConnectorOAuthStorage,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    ConnectorOAuth,
    SignInRequired,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import FastMCPConnectionStrategy
from umbod.core.connectors.downstream_mcp.connection import (
    DownstreamMcpConnectionConfiguration,
    NoAuthConnectionConfiguration,
)
from umbod.core.connectors.downstream_mcp.probe import ProbeFailed
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.probe import FastMCPDownstreamConnection
from umbod.core.connectors.downstream_mcp.models import OAuthCredentialState
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_CREDENTIAL_TABLE,
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
    EncryptedCredentialStoreService,
    SaveCredential,
)
from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


def document(endpoint: str = "https://tools.example/mcp", expired: bool = False) -> AuthorizationDocument:
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


def store_for(database: Database) -> EncryptedCredentialStore:
    return EncryptedCredentialStoreService(
        database,
        CONNECTOR_CREDENTIAL_TABLE,
        AuthenticatedTextCipher("oauth-test-key"),
    )


async def seed(store: EncryptedCredentialStore, connector_id: str = "one", expired: bool = False) -> SecretStr:
    value = DetachedConnectorOAuthStorage(document(expired=expired), "").export()
    await store.save(
        SaveCredential(
            credential=OAuthCredentialState(connector_id=connector_id, authorization=value)
        )
    )
    return value


@pytest.mark.asyncio
async def test_authorization_is_encrypted_and_survives_store_recreation(database: Database) -> None:
    original = await seed(store_for(database))
    reopened = store_for(database)
    restored = await reopened.get(ConnectorIdQuery(connector_id="one"))
    assert isinstance(restored, CredentialFound)
    assert isinstance(restored.credential, OAuthCredentialState)
    assert restored.credential.authorization == original
    async with database.read_session() as session:
        stored = await session.find_one(CONNECTOR_CREDENTIAL_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    assert stored is not None
    assert "old-access" not in stored.document
    assert "old-refresh" not in stored.document
    assert "old-access" not in restored.credential.model_dump_json()
    assert "old-refresh" not in repr(restored.credential)


@pytest.mark.asyncio
async def test_expired_token_refreshes_once_across_two_clients_and_persists(database: Database) -> None:
    store = store_for(database)
    await seed(store, expired=True)
    refreshes: list[httpx2.Request] = []

    async def handle(request: httpx2.Request) -> httpx2.Response:
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

    async def use() -> None:
        oauth = ConnectorOAuth(PersistedConnectorOAuthStorage(document(), "one", store_for(database)))
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle), auth=oauth) as client:
            assert (await client.post("https://tools.example/mcp")).status_code == 200

    await asyncio.gather(use(), use())
    assert len(refreshes) == 1
    saved = await store.get(ConnectorIdQuery(connector_id="one"))
    assert isinstance(saved, CredentialFound)
    assert isinstance(saved.credential, OAuthCredentialState)
    restored = AuthorizationDocument.model_validate_json(
        saved.credential.authorization.get_secret_value()
    )
    assert restored.tokens.refresh_token == "rotated-refresh"
    assert restored.expires_at > time.time()
    await use()
    assert len(refreshes) == 1


@pytest.mark.asyncio
async def test_stale_refresh_cannot_overwrite_new_sign_in_or_resurrect_deleted_connection(database: Database) -> None:
    store = store_for(database)
    original = await seed(store)
    replacement = SecretStr(document().model_dump_json())
    assert await store.replace_oauth_authorization("one", original, replacement)
    assert not await store.replace_oauth_authorization("one", original, SecretStr("stale"))
    await store.delete(ConnectorIdQuery(connector_id="one"))
    assert not await store.replace_oauth_authorization("one", replacement, original)


@pytest.mark.asyncio
async def test_authorization_is_scoped_to_connector_and_endpoint(database: Database) -> None:
    store = store_for(database)
    await seed(store)
    with pytest.raises(SignInRequired):
        await PersistedConnectorOAuthStorage(document(), "other", store).load()
    with pytest.raises(SignInRequired):
        await PersistedConnectorOAuthStorage(document("https://other.example/mcp"), "one", store).load()


@pytest.mark.asyncio
async def test_runtime_never_starts_browser_authorization() -> None:
    authorization = document()
    authorization.tokens = None
    oauth = ConnectorOAuth(DetachedConnectorOAuthStorage(authorization, ""))
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if str(request.url) == authorization.endpoint_url:
            return httpx2.Response(401)
        assert request.method == "GET"
        assert "/.well-known/" in request.url.path
        return httpx2.Response(404)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle), auth=oauth) as client:
        with pytest.raises(SignInRequired):
            await client.post(authorization.endpoint_url)
    assert requests
    assert str(requests[0].url) == authorization.endpoint_url


@pytest.mark.asyncio
async def test_nested_unauthorized_response_is_not_reported_as_invalid_mcp() -> None:
    response = httpx2.Response(401, request=httpx2.Request("POST", "https://tools.example/mcp"))
    error = httpx2.HTTPStatusError("unauthorized", request=response.request, response=response)

    class UnauthorizedClient:
        async def __aenter__(self) -> "UnauthorizedClient":
            raise ExceptionGroup("transport", [error])

        async def __aexit__(self, *args: object) -> None:
            return None

    class UnauthorizedConnection:
        def __init__(self) -> None:
            self.configuration: DownstreamMcpConnectionConfiguration = (
                NoAuthConnectionConfiguration(endpoint_url="https://tools.example/mcp")
            )

        def create(
            self, configuration: DownstreamMcpConnectionConfiguration
        ) -> FastMCPConnectionStrategy:
            self.configuration = configuration
            return self

        def create_client(self) -> Client:
            return cast(Client, UnauthorizedClient())

        def export_authorization(self, client: Client) -> SecretStr | None:
            return None

    failure = await FastMCPDownstreamConnection(True, 1, UnauthorizedConnection()).probe(
        NoAuthConnectionConfiguration(endpoint_url="https://tools.example/mcp")
    )
    assert failure == ProbeFailed(code="auth_rejected")
