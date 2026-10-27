from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
import pytest
from pydantic import ConfigDict, SecretStr
from umbod.proxies import Model
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.registry import InMemoryConnectorRegistry
from tests.support.connector_plugins import TestConnectorPlugin as test_connector
from umbod.mcp.connectors.native import (
    ConnectorRuntimeState,
    ConnectorRuntimeStateSynchronizer,
    HttpConnectorRuntimeStateSynchronizationSource,
    LocalConnectorRuntimeStateSynchronizationSource,
    SQLiteConnectorRuntimeStateReader,
)

class SlackAdminConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    workspace_name: str
    bot_token: SecretStr
    default_channel_id: str

class NestedSecretConfiguration(Model):
    credentials: dict[str, object]

@pytest.mark.asyncio
async def test_sqlite_reader_returns_registered_state_with_revealed_nested_secrets() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    reader = SQLiteConnectorRuntimeStateReader(InMemoryConnectorRegistry([test_connector.registration()], ['test']), configuration_store, publishing_store)
    await configuration_store.save_current_configuration('test', NestedSecretConfiguration(credentials={'primary': SecretStr('secret'), 'nested': [SecretStr('deeper')]}))
    await publishing_store.publish_connector('test')
    state = await reader.get_connector_runtime_state('test')
    assert state is not None
    assert state.display_name == 'Test Connector'
    assert state.available is True
    assert state.published is True
    assert state.configuration == {'credentials': {'primary': 'secret', 'nested': ['deeper']}}

@pytest.mark.asyncio
async def test_sqlite_reader_lists_registered_connectors() -> None:
    reader = SQLiteConnectorRuntimeStateReader(InMemoryConnectorRegistry([test_connector.registration()], ['test']), InMemoryConnectorCurrentConfigurationStore(), ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE))
    states = await reader.list_connector_runtime_states()
    assert [state.connector_id for state in states] == ['test']

@pytest.mark.asyncio
async def test_sqlite_reader_returns_none_for_unknown_connector() -> None:
    reader = SQLiteConnectorRuntimeStateReader(InMemoryConnectorRegistry([test_connector.registration()], ['test']), InMemoryConnectorCurrentConfigurationStore(), ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE))
    assert await reader.get_connector_runtime_state('unknown') is None

class RecordingRuntimeStateReader:

    def __init__(self, states: dict[str, ConnectorRuntimeState], single_requests: list[str]) -> None:
        self.states = states
        self.single_requests = single_requests

    async def get_connector_runtime_state(self, connector_id: str) -> ConnectorRuntimeState | None:
        self.single_requests.append(connector_id)
        return self.states.get(connector_id)

    async def list_connector_runtime_states(self) -> list[ConnectorRuntimeState]:
        return list(self.states.values())

class RecordingToolRegistry:

    def __init__(self) -> None:
        self.reconciled_connectors: list[str] = []
        self.reconciled_all = False

    def configuration_schema_for_connector(self, connector_id: str) -> type[Model] | None:
        if connector_id == 'slack':
            return SlackAdminConfiguration
        return None

    async def reconcile_connector(self, connector_id: str) -> None:
        self.reconciled_connectors.append(connector_id)

    async def reconcile_all(self) -> None:
        self.reconciled_all = True

def make_slack_runtime_state(published: bool) -> ConnectorRuntimeState:
    return ConnectorRuntimeState(connector_id='slack', available=True, published=published, configuration={'workspace_name': 'Acme', 'bot_token': 'xoxb-secret', 'default_channel_id': 'C123'})

def make_reader_with_slack_state(published: bool) -> RecordingRuntimeStateReader:
    return RecordingRuntimeStateReader(states={'slack': make_slack_runtime_state(published=published)}, single_requests=[])

ConnectorStores = tuple[InMemoryConnectorCurrentConfigurationStore, ConnectorPublishingStoreService]


def make_runtime_synchronizer(reader: RecordingRuntimeStateReader, target_stores: ConnectorStores, tool_registry: RecordingToolRegistry, source_stores: ConnectorStores | None) -> ConnectorRuntimeStateSynchronizer:
    synchronization_source = HttpConnectorRuntimeStateSynchronizationSource(reader) if source_stores is None else LocalConnectorRuntimeStateSynchronizationSource(source_stores[0], source_stores[1])
    return ConnectorRuntimeStateSynchronizer(reader=reader, configuration_store=target_stores[0], publishing_store=target_stores[1], tool_registry=tool_registry, synchronization_source=synchronization_source)

async def save_source_slack_configuration(configuration_store: InMemoryConnectorCurrentConfigurationStore, publishing_store: ConnectorPublishingStoreService) -> None:
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Acme', bot_token=SecretStr('xoxb-source'), default_channel_id='C123'))
    await publishing_store.publish_connector('slack')

async def make_source_slack_stores() -> tuple[InMemoryConnectorCurrentConfigurationStore, ConnectorPublishingStoreService]:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await save_source_slack_configuration(configuration_store=configuration_store, publishing_store=publishing_store)
    return (configuration_store, publishing_store)

@pytest.mark.asyncio
async def test_sync_all_updates_all_states_before_reconcile_all() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    tool_registry = RecordingToolRegistry()
    reader = make_reader_with_slack_state(published=False)
    runtime_synchronizer = make_runtime_synchronizer(reader=reader, target_stores=(configuration_store, publishing_store), tool_registry=tool_registry, source_stores=None)
    await runtime_synchronizer.sync_all()
    assert await configuration_store.get_current_configuration('slack') is not None
    assert await publishing_store.is_published('slack') is False
    assert tool_registry.reconciled_all is True
