import os
from pathlib import Path
from typing import cast

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from tests.support.persistence_contracts import row, table
from umbod.config import ConnectorStoreConfig, SQLiteConnectorStoreConfig
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered


def test_unrequested_application_fixtures_are_not_set_up(request: pytest.FixtureRequest) -> None:
    assert "installed_test_connector_plugins" not in request.fixturenames
    assert "isolated_connector_store_database" not in request.fixturenames
    assert "isolated_connector_store_directory" not in request.fixturenames


def test_allocated_database_path_does_not_change_configuration_or_create_storage(
    request: pytest.FixtureRequest,
) -> None:
    original_default = ConnectorStoreConfig().sqlite_path
    original_environment = os.environ.get("UMBOD_CONNECTOR_STORE_SQLITE_PATH")
    database_path = cast(Path, request.getfixturevalue("isolated_connector_store_database"))
    configuration = SQLiteConnectorStoreConfig(sqlite_path=str(database_path))

    assert configuration.sqlite_path == str(database_path)
    assert not database_path.exists()
    assert ConnectorStoreConfig().sqlite_path == original_default
    assert os.environ.get("UMBOD_CONNECTOR_STORE_SQLITE_PATH") == original_environment


def test_configuration_isolation_reuses_worker_directory_without_requesting_tmp_path(
    isolated_connector_store_database: Path,
    isolated_connector_store_directory: Path,
    request: pytest.FixtureRequest,
) -> None:
    assert isolated_connector_store_database.parent == isolated_connector_store_directory
    assert "tmp_path" not in request.fixturenames
    assert not isolated_connector_store_database.exists()


@pytest.mark.asyncio
async def test_runtime_construction_does_not_prepare_the_isolated_database(
    isolated_connector_store_database: Path,
) -> None:
    runtime = create_sqlite_runtime(isolated_connector_store_database)
    try:
        assert not isolated_connector_store_database.exists()
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("display_name", ["First", "Second"])
@pytest.mark.asyncio
async def test_explicit_preparation_provides_fresh_writable_store_state(
    prepared_connector_store_database: Path,
    isolated_connector_store_database: Path,
    display_name: str,
) -> None:
    assert prepared_connector_store_database == isolated_connector_store_database
    assert prepared_connector_store_database.is_file()
    runtime = create_sqlite_runtime(prepared_connector_store_database)
    try:
        await runtime.readiness.ensure_ready()
        fixture_table, _, _, _ = table("prepared_fixture_probe")
        await runtime.database.ensure_schema((fixture_table,))
        selection = Query(NoFilter(), AllFields(), Unordered())
        record = row("fixture-record", display_name)
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            assert tuple(await session.find_many(fixture_table, selection)) == ()
            await session.insert(fixture_table, InsertCommand(row=record))
            assert tuple(await session.find_many(fixture_table, selection)) == (record,)
    finally:
        await runtime.shutdown()
