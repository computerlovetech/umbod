from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from tests.support.persistence_contracts import row, table
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from umbod.infrastructure.connections import ConnectionPool, ConnectionPoolUnavailableError, ConnectionProvider, UnpooledConnectionProvider
from umbod.infrastructure.connections.sqlite import SQLiteConnectionDriver
from umbod.infrastructure.persistence.runtime import SQLitePersistenceRuntime
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase


class RecordingConnectionProvider:
    def __init__(self, connections: ConnectionProvider[aiosqlite.Connection]) -> None:
        self._connections = connections
        self.leases = 0
        self.initializations = 0
        self.shutdowns = 0

    async def initialize(self) -> None:
        self.initializations += 1
        await self._connections.initialize()

    async def close(self) -> None:
        self.shutdowns += 1
        await self._connections.close()

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        self.leases += 1
        async with self._connections.get_connection() as connection:
            yield connection


@pytest.fixture
def connections(tmp_path: Path) -> RecordingConnectionProvider:
    driver = SQLiteConnectionDriver(str(tmp_path / "injected.sqlite"), create_parent_dirs=False)
    return RecordingConnectionProvider(UnpooledConnectionProvider(driver.connect, driver.close))


@pytest.mark.asyncio
async def test_all_database_operations_lease_from_the_injected_provider(
    connections: RecordingConnectionProvider,
) -> None:
    database = SQLiteDatabase(connections)
    assert connections.leases == 0
    records, _, _, _ = table("injected_records")
    await database.ensure_schema((records,))
    expected = row("injected", "value")
    async with database.session(mode=TransactionMode.READ_WRITE) as writer:
        await writer.insert(records, InsertCommand(row=expected))
    async with database.read_session() as reader:
        assert await reader.find_many(records, Query(NoFilter(), AllFields(), Unordered())) == (expected,)
    async with database.schema_connection() as connection:
        async with connection.execute("SELECT count(*) FROM injected_records") as cursor:
            assert (await cursor.fetchone())[0] == 1
    assert connections.leases == 4
    assert connections.initializations == 0
    assert connections.shutdowns == 0


@pytest.mark.asyncio
async def test_database_does_not_initialize_an_unready_provider(tmp_path: Path) -> None:
    path = tmp_path / "not-opened.sqlite"
    connections = ConnectionPool(SQLiteConnectionDriver(str(path), create_parent_dirs=False), size=1)
    database = SQLiteDatabase(connections)
    try:
        with pytest.raises(ConnectionPoolUnavailableError):
            async with database.read_session():
                pytest.fail("an uninitialized provider must reject acquisition")
        assert not path.exists()
    finally:
        await connections.close()


@pytest.mark.asyncio
async def test_runtime_initializes_and_closes_the_injected_provider(
    connections: RecordingConnectionProvider,
) -> None:
    runtime = SQLitePersistenceRuntime(SQLiteDatabase(connections), connections)
    assert connections.initializations == 0
    try:
        await runtime.readiness.ensure_ready()
        assert connections.initializations == 1
        assert connections.leases > 0
        assert connections.shutdowns == 0
    finally:
        await runtime.shutdown()
    assert connections.shutdowns == 1
