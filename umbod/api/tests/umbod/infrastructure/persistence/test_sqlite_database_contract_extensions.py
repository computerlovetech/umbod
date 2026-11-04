import sqlite3
from contextlib import closing

from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from pathlib import Path
import pytest
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from tests.umbod.core.persistence.contract_support import row, serialized_claim_observations, table

@pytest.mark.asyncio
async def test_sqlite_persists_across_database_instances(tmp_path: Path) -> None:
    path = tmp_path / 'persisted.sqlite'
    (contract_table, _, _, _) = table('persisted_samples')
    writer = SQLiteDatabase(str(path), create_parent_dirs=True)
    await writer.ensure_schema((contract_table,))
    async with writer.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=row('persisted')))
    reader = SQLiteDatabase(str(path), create_parent_dirs=True)
    async with reader.session(mode=TransactionMode.READ_WRITE) as session:
        stored = await session.find_many(contract_table, Query(NoFilter(), AllFields(), Unordered()))
    assert stored == (row('persisted'),)

@pytest.mark.asyncio
async def test_sqlite_quotes_reserved_identifiers(tmp_path: Path) -> None:
    (contract_table, _, _, _) = table('select')
    database = SQLiteDatabase(str(tmp_path / 'reserved.sqlite'), create_parent_dirs=True)
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.insert(contract_table, InsertCommand(row=row('record'))) is True


@pytest.mark.asyncio
async def test_sqlite_serializes_read_check_upsert_claims_across_database_instances(tmp_path: Path) -> None:
    path = tmp_path / "shared-claims.sqlite"
    first = SQLiteDatabase(str(path), create_parent_dirs=True)
    second = SQLiteDatabase(str(path), create_parent_dirs=True)
    assert await serialized_claim_observations(first, second) == ("available", "claimed")


@pytest.mark.asyncio
async def test_sqlite_serialized_session_acquires_writer_lock_before_any_read(tmp_path: Path) -> None:
    path = tmp_path / "immediate-lock.sqlite"
    contract_table, _, _, _ = table("locked_records")
    database = SQLiteDatabase(str(path), create_parent_dirs=True)
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE):
        with closing(sqlite3.connect(path, timeout=0)) as contender:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                contender.execute("BEGIN IMMEDIATE")
