import sqlite3
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.downstream_mcp_connectors.test_unit_of_work_contract import _command, _sqlite
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("create", "delete"))
async def test_database_event_append_failure_rolls_back_aggregate(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "events.sqlite3"
    await prepared_sqlite_runtime(path)
    harness = await _sqlite(path, lambda phase: None)
    if mutation == "delete":
        await harness.unit_of_work.create(_command())
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON messaging_events BEGIN SELECT RAISE(ABORT, 'event append failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        if mutation == "create":
            await harness.unit_of_work.create(_command())
        else:
            await harness.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="alpha"))
    query = ConnectorIdQuery(connector_id="alpha")
    assert (await harness.definitions.get(query)).found == (mutation == "delete")
    assert (await harness.catalogs.get(query)).found == (mutation == "delete")
    assert len(await harness.events.list_after(0, 100)) == (1 if mutation == "delete" else 0)
