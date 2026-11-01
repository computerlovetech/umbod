import time
from types import SimpleNamespace
from typing import Self, cast

import httpx2
import pytest
from fastmcp import Client
from mcp.shared.auth import OAuthToken
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.adapters.credential_fakes import MemoryCredentialStore
from tests.umbod.core.downstream_mcp_connectors.adapters.test_oauth import document
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import (
    FastMCPDownstreamConnectionFactory,
    FastMCPOAuthConnection,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import ConnectorOAuth, SignInRequired
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage import AuthorizationDocument
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage_adapters import (
    DetachedConnectorOAuthStorage,
    PersistedConnectorOAuthStorage,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.probe import FastMCPDownstreamConnection
from umbod.core.connectors.downstream_mcp.connection import OAuthConnectionConfiguration
from umbod.core.connectors.downstream_mcp.management.preparation import DownstreamConnectorPreparation
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition, OAuthCredentialState


@pytest.mark.parametrize("persist_refresh", [True, False])
def test_factory_selects_explicit_storage_mode(persist_refresh: bool) -> None:
    configuration = OAuthConnectionConfiguration(
        endpoint_url="https://tools.example/mcp",
        connector_id="one",
        authorization=SecretStr(document().model_dump_json()),
        persist_refresh=persist_refresh,
    )
    strategy = FastMCPDownstreamConnectionFactory(True, MemoryCredentialStore(), oauth_enabled=True).create(configuration)
    oauth = strategy.create_client().transport.auth
    assert isinstance(oauth, ConnectorOAuth)
    expected_type = PersistedConnectorOAuthStorage if persist_refresh else DetachedConnectorOAuthStorage
    assert isinstance(oauth.storage, expected_type)
    assert oauth.storage.connector_id == "one"


@pytest.mark.parametrize("persist_refresh", [True, False])
def test_factory_validates_document_endpoint_for_each_storage_mode(persist_refresh: bool) -> None:
    configuration = OAuthConnectionConfiguration(
        endpoint_url="https://other.example/mcp",
        connector_id="one",
        authorization=SecretStr(document().model_dump_json()),
        persist_refresh=persist_refresh,
    )
    with pytest.raises(SignInRequired):
        FastMCPDownstreamConnectionFactory(True, MemoryCredentialStore(), oauth_enabled=True).create(configuration)


@pytest.mark.parametrize(
    "endpoint, connector_id",
    [("https://other.example/mcp", "one"), ("https://tools.example/mcp", "other")],
)
def test_direct_connection_rejects_mismatched_storage_identity(
    endpoint: str, connector_id: str,
) -> None:
    configuration = OAuthConnectionConfiguration(
        endpoint_url="https://tools.example/mcp",
        connector_id="one",
        authorization=SecretStr(document().model_dump_json()),
    )
    storage = DetachedConnectorOAuthStorage(
        AuthorizationDocument(endpoint_url=endpoint), connector_id
    )
    with pytest.raises(SignInRequired):
        FastMCPOAuthConnection(configuration, True, storage)


class RefreshingProbeClient:
    def __init__(self, oauth: ConnectorOAuth) -> None:
        self.oauth = oauth
        self.server_capabilities = SimpleNamespace(tools=None, prompts=None, resources=None)
        self.server_info = None

    async def __aenter__(self) -> Self:
        def handle(request: httpx2.Request) -> httpx2.Response:
            if str(request.url) == "https://auth.example/token":
                return httpx2.Response(200, json={
                    "access_token": "prepared_access",
                    "refresh_token": "prepared_refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                })
            assert request.headers["authorization"] == "Bearer prepared_access"
            return httpx2.Response(200)

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle), auth=self.oauth) as client:
            await client.post(self.oauth.storage.document.endpoint_url)
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_detached_probe_refresh_exports_into_preparation_without_shared_store_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryCredentialStore()
    shared = OAuthCredentialState(connector_id="one", authorization=SecretStr("unrelated_shared_state"))
    store.credentials["one"] = shared
    create_client = FastMCPOAuthConnection.create_client

    def refreshing_client(connection: FastMCPOAuthConnection) -> Client:
        oauth = create_client(connection).transport.auth
        assert isinstance(oauth, ConnectorOAuth)
        assert isinstance(oauth.storage, DetachedConnectorOAuthStorage)
        return cast(Client, RefreshingProbeClient(oauth))

    monkeypatch.setattr(FastMCPOAuthConnection, "create_client", refreshing_client)
    factory = FastMCPDownstreamConnectionFactory(True, store, oauth_enabled=True)
    preparation = DownstreamConnectorPreparation(FastMCPDownstreamConnection(True, 5, factory))
    definition = OAuthConnectorDefinition(
        connector_id="one",
        display_name="OAuth",
        endpoint_url="https://tools.example/mcp",
        tool_name_prefix="oauth",
        capability_description="Test",
        public_path="/mcp/proxies/one",
    )
    credential = OAuthCredentialState(
        connector_id="one", authorization=SecretStr(document(expired=True).model_dump_json())
    )
    before = time.time()
    prepared = await preparation.prepare_update(definition, credential)
    after = time.time()
    assert isinstance(prepared.credential, OAuthCredentialState)
    exported = AuthorizationDocument.model_validate_json(prepared.credential.authorization.get_secret_value())
    assert exported.tokens == OAuthToken(
        access_token="prepared_access", refresh_token="prepared_refresh", token_type="Bearer", expires_in=3600
    )
    assert before + 3600 <= exported.expires_at <= after + 3600
    assert store.reads == store.writes == 0
    assert store.credentials == {"one": shared}
