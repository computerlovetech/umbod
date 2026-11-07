import pytest

from tests.persistence_runtime import create_inmemory_runtime
from umbod.core.connectors.downstream_mcp.models import StaticBearerConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionStore,
    SaveConnectorDefinition,
    create_downstream_mcp_stores,
)


@pytest.mark.parametrize("display_name", ["First", "Second"])
@pytest.mark.asyncio
async def test_independent_runtime_provides_fresh_writable_connector_store(display_name: str) -> None:
    runtime = create_inmemory_runtime()
    try:
        await runtime.readiness.ensure_ready()
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
