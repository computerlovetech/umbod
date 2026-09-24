from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
import pytest
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, HttpConnectorRuntimeStateSourceStrategy, LocalConnectorRuntimeStateSourceStrategy, StoreBackedConnectorRuntimeStateSourceStrategy, resolve_connector_runtime_state_source_strategy

def test_runtime_state_source_without_stores_uses_http() -> None:
    strategy = resolve_connector_runtime_state_source_strategy(ConnectorRuntimeSourceStores(), HttpConnectorRuntimeStateSourceStrategy())
    assert isinstance(strategy, HttpConnectorRuntimeStateSourceStrategy)

def test_runtime_state_source_with_both_stores_uses_supplied_local_stores() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    strategy = resolve_connector_runtime_state_source_strategy(ConnectorRuntimeSourceStores(configuration_store, publishing_store), StoreBackedConnectorRuntimeStateSourceStrategy())
    assert isinstance(strategy, LocalConnectorRuntimeStateSourceStrategy)
    assert strategy.connector_configuration_store is configuration_store
    assert strategy.connector_publishing_store is publishing_store

@pytest.mark.parametrize('missing_store', ['configuration', 'publishing'])
def test_runtime_state_source_rejects_partial_store_pairs(missing_store: str) -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    source_stores = ConnectorRuntimeSourceStores(None, publishing_store) if missing_store == 'configuration' else ConnectorRuntimeSourceStores(configuration_store, None)
    with pytest.raises(ValueError, match='must provide both'):
        resolve_connector_runtime_state_source_strategy(source_stores, HttpConnectorRuntimeStateSourceStrategy())
