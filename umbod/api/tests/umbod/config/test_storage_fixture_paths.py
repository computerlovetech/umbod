from pathlib import Path

from umbod.config import SQLiteConnectorStoreConfig


def test_sqlite_configuration_uses_an_isolated_unprepared_path(
    isolated_connector_store_database: Path,
) -> None:
    configuration = SQLiteConnectorStoreConfig(sqlite_path=str(isolated_connector_store_database))
    assert isinstance(configuration, SQLiteConnectorStoreConfig)
    assert configuration.sqlite_path == str(isolated_connector_store_database)
    assert not isolated_connector_store_database.exists()
