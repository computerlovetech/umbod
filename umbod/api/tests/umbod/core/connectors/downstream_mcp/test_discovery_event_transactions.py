from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.messaging import reject_database_event_appends
from tests.umbod.core.connectors.downstream_mcp.test_unit_of_work_contract import _command, _database_harness
from umbod.core.persistence import Database
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("create", "delete"))
async def test_database_event_append_failure_rolls_back_aggregate(database: Database, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    harness = await _database_harness(database, lambda phase: None)
    if mutation == "delete":
        await harness.unit_of_work.create(_command())
    reject_database_event_appends(database, monkeypatch)
    with pytest.raises(RuntimeError, match="event append failed"):
        if mutation == "create":
            await harness.unit_of_work.create(_command())
        else:
            await harness.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="alpha"))
    query = ConnectorIdQuery(connector_id="alpha")
    assert (await harness.definitions.get(query)).found == (mutation == "delete")
    assert (await harness.catalogs.get(query)).found == (mutation == "delete")
    assert len(await harness.events.list_after(0, 100)) == (1 if mutation == "delete" else 0)
