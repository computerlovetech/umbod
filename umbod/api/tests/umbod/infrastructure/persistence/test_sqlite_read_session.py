import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from tests.umbod.core.persistence.contract_support import row, table


class ObservedSQLiteDatabase(SQLiteDatabase):
    def __init__(self, path: Path) -> None:
        super().__init__(str(path), create_parent_dirs=True)
        self.connections: list[aiosqlite.Connection] = []

    async def _connect(self) -> aiosqlite.Connection:
        connection = await super()._connect()
        self.connections.append(connection)
        return connection


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[ObservedSQLiteDatabase]:
    instance = ObservedSQLiteDatabase(tmp_path / "read.sqlite")
    contract_table, _, _, _ = table()
    await instance.ensure_schema((contract_table,))
    yield instance


@pytest.mark.asyncio
async def test_sqlite_read_connection_rejects_engine_writes_and_closes_on_exit(
    database: ObservedSQLiteDatabase,
) -> None:
    async with database.read_session():
        connection = database.connections[-1]
        with pytest.raises(aiosqlite.OperationalError, match="readonly"):
            await connection.execute("DELETE FROM typed_samples")
    with pytest.raises(ValueError, match="no active connection"):
        await connection.execute("SELECT 1")


@pytest.mark.asyncio
async def test_sqlite_snapshot_starts_at_first_read_without_reserving_writer(
    database: ObservedSQLiteDatabase,
) -> None:
    contract_table, _, _, _ = table()
    async with database.read_session() as reader:
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as writer:
            await writer.insert(contract_table, InsertCommand(row=row("committed", "value")))
        assert await reader.find_one(
            contract_table, Query(NoFilter(), AllFields(), Unordered()),
        ) == row("committed", "value")


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", (RuntimeError, asyncio.CancelledError))
async def test_sqlite_failed_read_session_setup_closes_connection(
    database: ObservedSQLiteDatabase, monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
) -> None:
    execute = aiosqlite.Connection.execute

    async def fail_begin(
        connection: aiosqlite.Connection, statement: str, *parameters: object,
    ) -> aiosqlite.Cursor:
        if statement == "BEGIN":
            raise error_type("read setup failed")
        return await execute(connection, statement, *parameters)

    monkeypatch.setattr(aiosqlite.Connection, "execute", fail_begin)
    with pytest.raises(error_type, match="read setup failed"):
        async with database.read_session():
            pytest.fail("read session should not open")
    with pytest.raises(ValueError, match="no active connection"):
        await database.connections[-1].execute("SELECT 1")
