import asyncio
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def installed_test_connector_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.support.connector_plugins import SlackConnectorPlugin, TestConnectorPlugin
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


@pytest.fixture
def isolated_connector_store_database(isolated_connector_store_directory: Path) -> Path:
    return isolated_connector_store_directory / f"{uuid4().hex}.sqlite3"


@pytest.fixture
def prepared_connector_store_database(
    isolated_connector_store_database: Path,
) -> Generator[Path, None, None]:
    from tests.persistence_runtime import prepared_sqlite_runtime

    runtime = asyncio.run(prepared_sqlite_runtime(isolated_connector_store_database))
    try:
        yield isolated_connector_store_database
    finally:
        asyncio.run(runtime.shutdown())
