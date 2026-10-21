import os
from pathlib import Path

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.config import ConnectorStoreConfig
from umbod.core.connectors.downstream_mcp.models import StaticBearerConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionStore,
    SaveConnectorDefinition,
    create_downstream_mcp_stores,
)


def test_database_is_not_created_by_configuration_isolation(
    isolated_connector_store_database: Path,
) -> None:
    assert not isolated_connector_store_database.exists()
    assert ConnectorStoreConfig().sqlite_path == str(isolated_connector_store_database)
    assert os.environ["UMBOD_CONNECTOR_STORE_SQLITE_PATH"] == str(
        isolated_connector_store_database
    )


def test_runtime_construction_does_not_prepare_the_isolated_database(
    isolated_connector_store_database: Path,
) -> None:
    create_sqlite_runtime(isolated_connector_store_database)

    assert not isolated_connector_store_database.exists()


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
        stores = await create_downstream_mcp_stores(
            credential_secret="fixture-test-secret",
            database=runtime.database,
        )
        definitions: ConnectorDefinitionStore = stores.definitions
        assert (await definitions.list()).definitions == ()
        definition = StaticBearerConnectorDefinition(
            connector_id="fixture-connector",
            display_name=display_name,
            endpoint_url="https://fixture.example.test/mcp",
        )

        await definitions.save(SaveConnectorDefinition(definition=definition))

        assert (await definitions.list()).definitions == (definition,)
    finally:
        await runtime.shutdown()
