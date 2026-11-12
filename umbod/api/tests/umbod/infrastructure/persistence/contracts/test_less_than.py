import pytest

from tests.support.persistence_contracts import SampleRow, table
from umbod.core.persistence import (
    AllFields, Database, DeleteQuery, InsertCommand, LessThan, NoFilter, OrderBy, Query, TransactionMode,
)


@pytest.mark.asyncio
async def test_less_than_filters_and_deletes_only_values_before_boundary(database: Database) -> None:
    contract_table, _, identifier, _ = table("less_than_contract")
    await database.ensure_schema((contract_table,))
    rows = tuple(SampleRow(owner_id="owner", record_id=value, payload=value) for value in ("a", "b", "c"))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        for row in rows:
            await session.insert(contract_table, InsertCommand(row=row))
        matched = await session.find_many(
            contract_table, Query(LessThan(identifier, "b"), AllFields(), OrderBy((identifier,))),
        )
        assert tuple(matched) == rows[:1]
        assert await session.delete(contract_table, DeleteQuery(LessThan(identifier, "b"))) == 1
    async with database.read_session() as session:
        remaining = await session.find_many(contract_table, Query(NoFilter(), AllFields(), OrderBy((identifier,))))
        assert tuple(remaining) == rows[1:]
