from umbod.core.configuration.persistence.stores.schema import CONNECTOR_CONFIGURATION_TABLE
from umbod.core.configuration.persistence.stores.service import EncryptedConnectorConfigurationStoreService
from tests.persistence_runtime import create_inmemory_runtime
from dataclasses import dataclass
from typing import Any
import pytest
from umbod_sdk.connectors.proxies import Model
from umbod.core.configuration import ConnectorConfigurationDecryptionError, ConnectorConfigurationNotFoundError, ConnectorConfigurationPermissionError, ConnectorConfigurationRegistry, ConnectorConfigurationSecretUnavailableError, ConnectorConfigurationService, ConnectorConfigurationValidationError, EnvironmentConnectorConfigurationSecret, UnavailableConnectorConfigurationSecret, UnknownConnectorConfigurationError

class SlackConfiguration(Model):
    name: str = 'Acme'
    allowed_channel_ids: list[str]

class GitHubConfiguration(Model):
    name: str
    repositories: list[str]

class DemoConfiguration(Model):
    enabled: bool = True
    label: str = 'default'

class ChangedSlackConfiguration(Model):
    name: str = 'Acme'
    allowed_channel_ids: list[int]

class SourceEnvelope(Model):
    payload: dict[str, Any]

@dataclass(frozen=True)
class ServiceDependencies:
    registry: ConnectorConfigurationRegistry
    store: EncryptedConnectorConfigurationStoreService

@pytest.fixture
def configuration_service() -> ConnectorConfigurationService:
    return _service(secret='connector-secret')

@pytest.mark.asyncio
async def test_administrator_stores_valid_json_configuration_for_a_connector(configuration_service: ConnectorConfigurationService) -> None:
    result = await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'name': 'Acme', 'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    supplied = await configuration_service.get_connector_configuration('slack', SlackConfiguration)
    assert result.accepted is True
    assert supplied.name == 'Acme'
    assert supplied.allowed_channel_ids == ['C-PROJECT-ALPHA']

@pytest.mark.asyncio
async def test_connector_receives_decrypted_validated_configuration(configuration_service: ConnectorConfigurationService) -> None:
    await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'name': 'Acme', 'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    supplied = await configuration_service.get_connector_configuration('slack', SlackConfiguration)
    assert supplied == SlackConfiguration(name='Acme', allowed_channel_ids=['C-PROJECT-ALPHA'])

@pytest.mark.asyncio
async def test_different_connectors_use_different_configuration_schemas() -> None:
    registry = ConnectorConfigurationRegistry(schemas={'slack': SlackConfiguration, 'github': GitHubConfiguration})
    dependencies = ServiceDependencies(registry, EncryptedConnectorConfigurationStoreService(create_inmemory_runtime().database, CONNECTOR_CONFIGURATION_TABLE))
    service = _service(secret='connector-secret', dependencies=dependencies)
    await service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    await service.configure_connector(actor_role='administrator', connector_id='github', json_configuration={'name': 'computerlove', 'repositories': ['umbod']})
    slack = await service.get_connector_configuration('slack', SlackConfiguration)
    github = await service.get_connector_configuration('github', GitHubConfiguration)
    assert slack.allowed_channel_ids == ['C-PROJECT-ALPHA']
    assert github.name == 'computerlove'
    assert github.repositories == ['umbod']

@pytest.mark.asyncio
async def test_connector_accepts_empty_json_object_when_schema_allows_defaults() -> None:
    registry = ConnectorConfigurationRegistry(schemas={'demo': DemoConfiguration})
    dependencies = ServiceDependencies(registry, EncryptedConnectorConfigurationStoreService(create_inmemory_runtime().database, CONNECTOR_CONFIGURATION_TABLE))
    service = _service(secret='connector-secret', dependencies=dependencies)
    await service.configure_connector(actor_role='administrator', connector_id='demo', json_configuration={})
    supplied = await service.get_connector_configuration('demo', DemoConfiguration)
    assert supplied == DemoConfiguration(enabled=True, label='default')

@pytest.mark.asyncio
async def test_replacing_valid_configuration_overwrites_previous_active_configuration(configuration_service: ConnectorConfigurationService) -> None:
    await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'name': 'Acme', 'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'name': 'Acme', 'allowed_channel_ids': ['C-SUPPORT-BETA']})
    supplied = await configuration_service.get_connector_configuration('slack', SlackConfiguration)
    assert supplied.allowed_channel_ids == ['C-SUPPORT-BETA']
    assert 'C-PROJECT-ALPHA' not in supplied.allowed_channel_ids

@pytest.mark.asyncio
async def test_configuration_can_be_supplied_from_any_json_source() -> None:
    service = _service(secret='connector-secret')
    api_request = SourceEnvelope(payload={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    file_import = SourceEnvelope(payload={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    in_memory_caller = SourceEnvelope(payload={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    for envelope in [api_request, file_import, in_memory_caller]:
        await service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration=envelope.payload)
        supplied = await service.get_connector_configuration('slack', SlackConfiguration)
        assert supplied.allowed_channel_ids == ['C-PROJECT-ALPHA']

@pytest.mark.asyncio
async def test_invalid_json_configuration_is_rejected_with_validation_details(configuration_service: ConnectorConfigurationService) -> None:
    with pytest.raises(ConnectorConfigurationValidationError) as error:
        await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': 'C-PROJECT-ALPHA'})
    assert 'allowed_channel_ids' in str(error.value.validation_details)
    with pytest.raises(ConnectorConfigurationNotFoundError):
        await configuration_service.get_connector_configuration('slack', SlackConfiguration)

@pytest.mark.asyncio
async def test_invalid_replacement_keeps_previous_valid_configuration_unchanged(configuration_service: ConnectorConfigurationService) -> None:
    await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    with pytest.raises(ConnectorConfigurationValidationError):
        await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': 'C-SUPPORT-BETA'})
    supplied = await configuration_service.get_connector_configuration('slack', SlackConfiguration)
    assert supplied.allowed_channel_ids == ['C-PROJECT-ALPHA']

@pytest.mark.asyncio
async def test_unknown_connector_configuration_is_rejected() -> None:
    service = _service(secret='connector-secret')
    with pytest.raises(UnknownConnectorConfigurationError):
        await service.configure_connector(actor_role='administrator', connector_id='unknown', json_configuration={'enabled': True})
    assert await service.store.get_encrypted_configuration('unknown') is None

@pytest.mark.asyncio
async def test_configuration_cannot_be_stored_when_encryption_secret_is_unavailable() -> None:
    service = _service(secret=None)
    with pytest.raises(ConnectorConfigurationSecretUnavailableError):
        await service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    assert await service.store.get_encrypted_configuration('slack') is None

@pytest.mark.asyncio
async def test_stored_configuration_cannot_be_supplied_when_decryption_fails() -> None:
    store = EncryptedConnectorConfigurationStoreService(create_inmemory_runtime().database, CONNECTOR_CONFIGURATION_TABLE)
    registry = ConnectorConfigurationRegistry(schemas={'slack': SlackConfiguration})
    dependencies = ServiceDependencies(registry, store)
    writer = _service(secret='original-secret', dependencies=dependencies)
    reader = _service(secret='changed-secret', dependencies=dependencies)
    await writer.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    with pytest.raises(ConnectorConfigurationDecryptionError):
        await reader.get_connector_configuration('slack', SlackConfiguration)

@pytest.mark.asyncio
async def test_administrator_can_configure_a_connector(configuration_service: ConnectorConfigurationService) -> None:
    result = await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    assert result.accepted is True

@pytest.mark.asyncio
async def test_non_administrator_cannot_configure_a_connector(configuration_service: ConnectorConfigurationService) -> None:
    with pytest.raises(ConnectorConfigurationPermissionError):
        await configuration_service.configure_connector(actor_role='developer', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    assert await configuration_service.store.get_encrypted_configuration('slack') is None

@pytest.mark.asyncio
async def test_stored_configuration_is_encrypted_rather_than_plaintext(configuration_service: ConnectorConfigurationService) -> None:
    await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    encrypted = await configuration_service.store.get_encrypted_configuration('slack')
    assert encrypted is not None
    assert encrypted.ciphertext != ''
    assert 'C-PROJECT-ALPHA' not in encrypted.ciphertext

@pytest.mark.asyncio
async def test_one_connector_has_one_active_configuration(configuration_service: ConnectorConfigurationService) -> None:
    await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    await configuration_service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-SUPPORT-BETA']})
    supplied = await configuration_service.get_connector_configuration('slack', SlackConfiguration)
    assert await configuration_service.store.count_configurations_for_connector('slack') == 1
    assert supplied.allowed_channel_ids == ['C-SUPPORT-BETA']

@pytest.mark.asyncio
async def test_connector_configuration_is_not_supplied_from_connector_specific_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SLACK_ALLOWED_CHANNEL_IDS', 'C-PRIVATE-LEADERSHIP')
    service = _service(secret='connector-secret')
    await service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    supplied = await service.get_connector_configuration('slack', SlackConfiguration)
    assert supplied.allowed_channel_ids == ['C-PROJECT-ALPHA']
    assert 'C-PRIVATE-LEADERSHIP' not in supplied.allowed_channel_ids

@pytest.mark.asyncio
async def test_stored_configuration_is_revalidated_before_being_supplied() -> None:
    store = EncryptedConnectorConfigurationStoreService(create_inmemory_runtime().database, CONNECTOR_CONFIGURATION_TABLE)
    registry = ConnectorConfigurationRegistry(schemas={'slack': SlackConfiguration})
    service = _service(secret='connector-secret', dependencies=ServiceDependencies(registry, store))
    await service.configure_connector(actor_role='administrator', connector_id='slack', json_configuration={'allowed_channel_ids': ['C-PROJECT-ALPHA']})
    changed_registry = ConnectorConfigurationRegistry(schemas={'slack': ChangedSlackConfiguration})
    changed_dependencies = ServiceDependencies(changed_registry, store)
    changed_service = _service(secret='connector-secret', dependencies=changed_dependencies)
    with pytest.raises(ConnectorConfigurationValidationError):
        await changed_service.get_connector_configuration('slack', ChangedSlackConfiguration)

def _service(secret: str | None, dependencies: ServiceDependencies | None=None) -> ConnectorConfigurationService:
    resolved_dependencies = dependencies or ServiceDependencies(ConnectorConfigurationRegistry(schemas={'slack': SlackConfiguration}), EncryptedConnectorConfigurationStoreService(create_inmemory_runtime().database, CONNECTOR_CONFIGURATION_TABLE))
    configuration_secret = EnvironmentConnectorConfigurationSecret.from_value(secret) if secret is not None else UnavailableConnectorConfigurationSecret()
    return ConnectorConfigurationService(registry=resolved_dependencies.registry, store=resolved_dependencies.store, secret=configuration_secret)
