from typing import cast

import pytest

from umbod.core.persistence import (
    AllFields,
    Database,
    InsertCommand,
    NoFilter,
    Query,
    TransactionMode,
    Unordered,
)
from tests.umbod.core.persistence.contract_support import ScalarRow, scalar_table


@pytest.mark.parametrize("number", [-(2**63), 2**63 - 1])
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("optional_text", [None, "text"])
@pytest.mark.asyncio
async def test_portable_scalar_values_round_trip(
    database: Database, number: int, enabled: bool, optional_text: str | None
) -> None:
    contract_table = scalar_table()
    expected = ScalarRow(
        record_id=f"{number}_{enabled}_{optional_text}",
        number=number,
        enabled=enabled,
        optional_text=optional_text,
    )
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=expected))
        stored = await session.find_one(contract_table, Query(NoFilter(), AllFields(), Unordered()))
    assert stored == expected


@pytest.mark.parametrize("number", [-(2**63) - 1, 2**63])
@pytest.mark.asyncio
async def test_integer_values_outside_signed_64_bit_range_are_rejected(
    database: Database, number: int
) -> None:
    contract_table = scalar_table()
    invalid = ScalarRow(record_id="invalid", number=number, enabled=True, optional_text=None)
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        with pytest.raises(TypeError, match="signed 64-bit"):
            await session.insert(contract_table, InsertCommand(row=invalid))


@pytest.mark.asyncio
async def test_invalid_boolean_runtime_value_is_rejected(database: Database) -> None:
    contract_table = scalar_table()
    invalid = ScalarRow.model_construct(
        record_id="invalid", number=0, enabled=cast(bool, 1), optional_text=None
    )
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        with pytest.raises(TypeError, match="expected bool"):
            await session.insert(contract_table, InsertCommand(row=invalid))
