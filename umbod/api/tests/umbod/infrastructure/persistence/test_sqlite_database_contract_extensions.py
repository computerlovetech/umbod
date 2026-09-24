from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from pathlib import Path
import pytest
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from tests.umbod.core.persistence.contract_support import row, table

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
