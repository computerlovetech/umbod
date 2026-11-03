import time

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from pydantic import SecretStr

from tests.umbod.core.connectors.downstream_mcp.adapters.credential_fakes import MemoryCredentialStore
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import SignInRequired
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage import AuthorizationDocument
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage_adapters import (
    DetachedConnectorOAuthStorage,
    PersistedConnectorOAuthStorage,
)
from umbod.core.connectors.downstream_mcp.models import NoAuthCredentialState, OAuthCredentialState

pytestmark = pytest.mark.asyncio
ENDPOINT = "https://tools.example/mcp"


def persisted_storage(store: MemoryCredentialStore) -> PersistedConnectorOAuthStorage:
    return PersistedConnectorOAuthStorage(AuthorizationDocument(endpoint_url=ENDPOINT), "one", store)


def authorization(access_token: str) -> SecretStr:
    return SecretStr(AuthorizationDocument(
        endpoint_url=ENDPOINT,
        tokens=OAuthToken(access_token=access_token, token_type="Bearer"),
    ).model_dump_json(indent=2))


def seed(store: MemoryCredentialStore, value: SecretStr) -> None:
    store.credentials["one"] = OAuthCredentialState(connector_id="one", authorization=value)


async def test_persisted_load_reloads_latest_authorization_and_compares_exact_bytes() -> None:
    store = MemoryCredentialStore()
    storage = persisted_storage(store)
    seed(store, authorization("first"))
    await storage.load()
    seed(store, authorization("latest"))
    await storage.load()
    assert (await storage.get_tokens()).access_token == "latest"
    await storage.set_tokens(OAuthToken(access_token="refreshed", token_type="Bearer"))
    assert store.credentials["one"].authorization == storage.export()


@pytest.mark.parametrize("replacement", ["stale", "deleted", "wrong_kind"])
async def test_persisted_save_rejects_replaced_or_deleted_credentials(replacement: str) -> None:
    store = MemoryCredentialStore()
    seed(store, authorization("loaded"))
    storage = persisted_storage(store)
    await storage.load()
    if replacement == "stale":
        seed(store, authorization("new_sign_in"))
    elif replacement == "deleted":
        store.credentials.clear()
    else:
        store.credentials["one"] = NoAuthCredentialState(connector_id="one")
    expected = store.credentials.copy()
    with pytest.raises(SignInRequired):
        await storage.set_tokens(OAuthToken(access_token="stale_refresh", token_type="Bearer"))
    assert store.credentials == expected


async def test_repeated_saves_advance_expected_authorization() -> None:
    store = MemoryCredentialStore()
    seed(store, authorization("loaded"))
    storage = persisted_storage(store)
    await storage.load()
    await storage.set_tokens(OAuthToken(access_token="first", token_type="Bearer"))
    await storage.set_client_info(OAuthClientInformationFull(client_id="registered"))
    await storage.set_tokens(OAuthToken(access_token="second", token_type="Bearer"))
    assert store.writes == 3
    assert store.credentials["one"].authorization == storage.export()


@pytest.mark.parametrize("invalid", ["missing", "wrong_kind", "wrong_endpoint"])
async def test_persisted_load_fails_closed(invalid: str) -> None:
    store = MemoryCredentialStore()
    seed(store, authorization("loaded"))
    storage = persisted_storage(store)
    await storage.load()
    if invalid == "missing":
        store.credentials.clear()
    elif invalid == "wrong_kind":
        store.credentials["one"] = NoAuthCredentialState(connector_id="one")
    else:
        seed(store, SecretStr(AuthorizationDocument(endpoint_url="https://other.example/mcp").model_dump_json()))
    with pytest.raises(SignInRequired):
        await storage.load()
    await storage.save()
    assert store.writes == 0


async def test_save_before_load_does_not_write_or_create_credentials() -> None:
    store = MemoryCredentialStore()
    storage = persisted_storage(store)
    await storage.set_tokens(OAuthToken(access_token="local", token_type="Bearer"))
    await storage.set_client_info(OAuthClientInformationFull(client_id="local"))
    await storage.save()
    assert store.reads == store.writes == 0
    assert store.credentials == {}


async def test_detached_setters_and_export_preserve_latest_sdk_document() -> None:
    storage = DetachedConnectorOAuthStorage(AuthorizationDocument(endpoint_url=ENDPOINT), "one")
    await storage.load()
    tokens = OAuthToken(access_token="local", refresh_token="rotated", token_type="Bearer", expires_in=300)
    client_info = OAuthClientInformationFull(client_id="registered")
    before = time.time()
    await storage.set_tokens(tokens)
    await storage.set_client_info(client_info)
    storage.document.metadata = OAuthMetadata(
        issuer="https://auth.example",
        authorization_endpoint="https://auth.example/authorize",
        token_endpoint="https://auth.example/token",
        response_types_supported=["code"],
    )
    storage.document.authorization_server = "https://auth.example"
    await storage.save()
    await storage.load()
    exported = AuthorizationDocument.model_validate_json(storage.export().get_secret_value())
    assert await storage.get_tokens() == exported.tokens == tokens
    assert await storage.get_client_info() == exported.client_info == client_info
    assert before + 300 <= exported.expires_at <= time.time() + 300
    assert exported.metadata == storage.document.metadata
    assert exported.authorization_server == "https://auth.example"
    await storage.set_tokens(OAuthToken(access_token="no_expiry", token_type="Bearer"))
    assert storage.document.expires_at is None
