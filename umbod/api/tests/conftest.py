from umbod.config.app import ConnectorStoreConfig
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.support.connector_plugins import SlackConnectorPlugin, TestConnectorPlugin


@pytest.fixture(autouse=True)
def installed_test_connector_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    from umbod.mcp.connectors import default_runtime
    from umbod.mcp import public_app, runtime_options
    from umbod.rest import factories

    def load_test_plugins(include_diagnostics: bool = False) -> list[object]:
        return [TestConnectorPlugin, SlackConnectorPlugin]

    for module in (default_runtime, public_app, runtime_options, factories):
        monkeypatch.setattr(module, 'load_connector_plugins', load_test_plugins)


@pytest.fixture(autouse=True)
def isolated_connector_store_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    if request.node.name in {
        'test_sqlite_path_derived_from_data_dir',
        'test_connector_store_defaults_to_inmemory',
    }:
        yield
        return
    sqlite_path = str(tmp_path / 'umbod.sqlite3')
    sqlite_path_field = ConnectorStoreConfig.model_fields['sqlite_path']
    original_default = sqlite_path_field.default
    monkeypatch.setenv('UMBOD_CONNECTOR_STORE_SQLITE_PATH', sqlite_path)
    sqlite_path_field.default = sqlite_path
    ConnectorStoreConfig.model_rebuild(force=True)
    import asyncio

    asyncio.run(prepared_sqlite_runtime(sqlite_path))
    try:
        yield
    finally:
        sqlite_path_field.default = original_default
        ConnectorStoreConfig.model_rebuild(force=True)
