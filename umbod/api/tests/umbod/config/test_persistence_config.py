import pytest
from pydantic import ValidationError

from umbod.config import (
    AppConfig,
    ConnectorStoreConfig,
    InMemoryConnectorStoreConfig,
    SQLiteConnectorStoreConfig,
)


def test_default_connector_store_preserves_serialized_shape() -> None:
    config = AppConfig()

    assert isinstance(config.connector_store, InMemoryConnectorStoreConfig)
    assert config.connector_store.model_dump() == {
        "type": "inmemory",
        "sqlite_path": ".data/umbod.sqlite3",
    }


def test_sqlite_connector_store_is_discriminated() -> None:
    config = AppConfig(connector_store={"type": "sqlite", "sqlite_path": "store.sqlite3"})

    assert isinstance(config.connector_store, SQLiteConnectorStoreConfig)
    assert config.connector_store.type == "sqlite"
    assert config.connector_store.sqlite_path == "store.sqlite3"


def test_legacy_connector_store_instance_remains_accepted() -> None:
    legacy = ConnectorStoreConfig(type="sqlite", sqlite_path="legacy.sqlite3")

    config = AppConfig(connector_store=legacy)

    assert isinstance(config.connector_store, SQLiteConnectorStoreConfig)
    assert config.connector_store.model_dump() == legacy.model_dump()


def test_unsupported_connector_store_backend_fails_validation() -> None:
    with pytest.raises(ValidationError):
        AppConfig(connector_store={"type": "postgresql"})
