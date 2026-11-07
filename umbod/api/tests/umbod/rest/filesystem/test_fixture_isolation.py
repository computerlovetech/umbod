import pytest

from umbod.config import InMemoryConnectorStoreConfig, PersistenceConfig


def test_inmemory_configuration_does_not_request_a_sqlite_path(
    filesystem_persistence_config: PersistenceConfig, request: pytest.FixtureRequest,
) -> None:
    assert isinstance(filesystem_persistence_config, InMemoryConnectorStoreConfig)
    assert "isolated_connector_store_database" not in request.fixturenames
    assert "isolated_connector_store_directory" not in request.fixturenames
