import asyncio
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest

from umbod.config.app import ConnectorStoreConfig

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.support.connector_plugins import SlackConnectorPlugin, TestConnectorPlugin


@pytest.fixture(autouse=True)
def installed_test_connector_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    from umbod.mcp.connectors.native import default_runtime
    from umbod.mcp import public_app, runtime_options
    from umbod.rest import factories

    def load_test_plugins(include_diagnostics: bool = False) -> list[object]:
        return [TestConnectorPlugin, SlackConnectorPlugin]

    for module in (default_runtime, public_app, runtime_options, factories):
        monkeypatch.setattr(module, 'load_connector_plugins', load_test_plugins)


@pytest.fixture(scope="session")
def isolated_connector_store_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("connector-store")


@pytest.fixture(autouse=True)
def isolated_connector_store_database(
    monkeypatch: pytest.MonkeyPatch,
    isolated_connector_store_directory: Path,
    request: pytest.FixtureRequest,
) -> Generator[Path, None, None]:
    database_path = isolated_connector_store_directory / f"{uuid4().hex}.sqlite3"
    if request.node.name in {
        'test_sqlite_path_derived_from_data_dir',
        'test_connector_store_defaults_to_inmemory',
    }:
        yield database_path
        return
    sqlite_path = str(database_path)
    sqlite_path_field = ConnectorStoreConfig.model_fields['sqlite_path']
    original_default = sqlite_path_field.default
    monkeypatch.setenv('UMBOD_CONNECTOR_STORE_SQLITE_PATH', sqlite_path)
    sqlite_path_field.default = sqlite_path
    ConnectorStoreConfig.model_rebuild(force=True)
    try:
        yield database_path
    finally:
        sqlite_path_field.default = original_default
        ConnectorStoreConfig.model_rebuild(force=True)


@pytest.fixture
def prepared_connector_store_database(
    isolated_connector_store_database: Path,
) -> Generator[Path, None, None]:
    runtime = asyncio.run(prepared_sqlite_runtime(isolated_connector_store_database))
    try:
        yield isolated_connector_store_database
    finally:
        asyncio.run(runtime.shutdown())
