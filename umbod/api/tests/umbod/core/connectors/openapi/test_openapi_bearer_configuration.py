from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_TABLE
from umbod.core.configuration.persistence.stores.service import EncryptedConnectorConfigurationStoreService
from tests.persistence_runtime import create_inmemory_runtime
import pytest
from pydantic import SecretStr
from umbod.core.configuration import ConnectorConfigurationRegistry, ConnectorConfigurationService, EnvironmentConnectorConfigurationSecret
from umbod.core.connectors.openapi.management import OpenApiBearerConfiguration, OpenApiConfigurationAdapter
from umbod.core.connectors.openapi.execution import BearerOpenApiRequestAuthenticator, OutboundRequest, TrustedBearerAuthorization
pytestmark = pytest.mark.asyncio

def _request() -> OutboundRequest:
    return OutboundRequest(method='GET', url='https://api.example.test/items', headers={}, json_body={}, has_json_body=False, timeout_seconds=1, maximum_response_bytes=100, approved_hosts=('api.example.test',))

def _adapter() -> tuple[OpenApiConfigurationAdapter, EncryptedConnectorConfigurationStoreService]:
    store = EncryptedConnectorConfigurationStoreService(create_inmemory_runtime().database, CONNECTOR_CONFIGURATION_TABLE)
    service = ConnectorConfigurationService(registry=ConnectorConfigurationRegistry({'openapi': OpenApiBearerConfiguration}), store=store, secret=EnvironmentConnectorConfigurationSecret.from_value('test-secret'))
    return (OpenApiConfigurationAdapter(service), store)

async def test_configuration_encrypts_token_and_resolves_secret_value() -> None:
    (adapter, store) = _adapter()
    await adapter.configure('billing', SecretStr('  token-value  '))
    encrypted = await store.get_encrypted_configuration('billing')
    assert encrypted is not None
    assert 'token-value' not in encrypted.ciphertext
    resolved = await adapter.resolve('billing')
    assert resolved is not None
    assert resolved.bearer_token.get_secret_value() == 'token-value'
    assert 'token-value' not in repr(resolved)

async def test_blank_configuration_preserves_existing_token() -> None:
    (adapter, _) = _adapter()
    await adapter.configure('billing', SecretStr('first-token'))
    result = await adapter.configure('billing', SecretStr('   '))
    assert result.configured is True
    resolved = await adapter.resolve('billing')
    assert resolved is not None
    assert resolved.bearer_token.get_secret_value() == 'first-token'

async def test_authenticator_uses_no_authentication_when_configuration_is_missing() -> None:
    (adapter, _) = _adapter()
    authenticated = await BearerOpenApiRequestAuthenticator(adapter).authenticate('billing', _request())
    assert authenticated.authorization.kind == 'none'

async def test_authenticator_adds_typed_trusted_bearer_after_compilation() -> None:
    (adapter, _) = _adapter()
    await adapter.configure('billing', SecretStr('trusted-token'))
    authenticated = await BearerOpenApiRequestAuthenticator(adapter).authenticate('billing', _request())
    assert isinstance(authenticated.authorization, TrustedBearerAuthorization)
    assert authenticated.authorization.token == SecretStr('trusted-token')
    assert 'authorization' not in authenticated.headers
