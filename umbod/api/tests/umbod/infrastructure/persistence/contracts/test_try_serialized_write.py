import asyncio

import pytest

from tests.support.persistence_contracts import row, table
from umbod.core.persistence import (
    AllFields, Database, InsertCommand, NoFilter, PersistenceBusyError, Query,
    TransactionMode, Unordered,
)


@pytest.mark.asyncio
async def test_try_serialized_write_fails_promptly_under_contention_and_remains_atomic(database: Database) -> None:
    records, _, _, _ = table("try_serialized")
    await database.ensure_schema((records,))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE):
        async with asyncio.timeout(0.5):
            with pytest.raises(PersistenceBusyError):
                async with database.session(mode=TransactionMode.TRY_SERIALIZED_WRITE):
                    pytest.fail("Contended best-effort transaction acquired the write lock")
    with pytest.raises(RuntimeError, match="rollback"):
        async with database.session(mode=TransactionMode.TRY_SERIALIZED_WRITE) as session:
            await session.insert(records, InsertCommand(row=row("discarded", "value")))
            raise RuntimeError("rollback")
    async with database.session(mode=TransactionMode.TRY_SERIALIZED_WRITE) as session:
        await session.insert(records, InsertCommand(row=row("committed", "value")))
    async with database.read_session() as session:
        found = await session.find_many(records, Query(NoFilter(), AllFields(), Unordered()))
        assert tuple(found) == (row("committed", "value"),)
