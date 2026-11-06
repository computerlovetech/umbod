from pathlib import Path
from typing import cast

import pytest

from umbod.config import InMemoryConnectorStoreConfig, PersistenceConfig, SQLiteConnectorStoreConfig


@pytest.mark.parametrize("filesystem_persistence_config", ["inmemory"], indirect=True)
def test_inmemory_configuration_does_not_request_a_sqlite_path(
    filesystem_persistence_config: PersistenceConfig, request: pytest.FixtureRequest,
) -> None:
    assert isinstance(filesystem_persistence_config, InMemoryConnectorStoreConfig)
    assert "isolated_connector_store_database" not in request.fixturenames
    assert "isolated_connector_store_directory" not in request.fixturenames


@pytest.mark.parametrize("filesystem_persistence_config", ["sqlite"], indirect=True)
def test_sqlite_configuration_uses_an_isolated_unprepared_path(
    filesystem_persistence_config: PersistenceConfig, request: pytest.FixtureRequest,
) -> None:
    assert isinstance(filesystem_persistence_config, SQLiteConnectorStoreConfig)
    database_path = cast(Path, request.getfixturevalue("isolated_connector_store_database"))
    assert filesystem_persistence_config.sqlite_path == str(database_path)
    assert not database_path.exists()
