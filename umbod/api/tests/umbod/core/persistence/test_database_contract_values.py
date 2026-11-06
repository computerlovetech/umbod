from typing import cast

import pytest

from umbod.core.persistence import (
    AllFields,
    Database,
    Equals,
    Fields,
    InsertCommand,
    NoFilter,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from tests.umbod.core.persistence.contract_support import ScalarKey, ScalarRow, ScalarValuesResult, scalar_table


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


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.asyncio
async def test_upsert_insert_and_conflict_update_preserve_typed_scalar_projection(
    database: Database, enabled: bool,
) -> None:
    contract_table = scalar_table()
    initial = ScalarRow(
        record_id="updated", number=7, enabled=enabled, optional_text="2026-01-01T00:00:00+00:00",
    )
    updated = initial.model_copy(update={
        "number": 42, "enabled": not enabled, "optional_text": "2026-01-02T00:00:00+00:00",
    })
    key = ScalarKey(record_id=initial.record_id)
    target = Equals(contract_table.key_codec.fields[0], initial.record_id)
    projection = Fields(ScalarValuesResult, contract_table.row_codec.fields[1:3])
    await database.ensure_schema((contract_table,))

    for expected in (initial, updated):
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(contract_table, UpsertCommand(key=key, row=expected))
        async with database.read_session() as session:
            assert await session.find_many(contract_table, Query(NoFilter(), AllFields(), Unordered())) == (expected,)
            assert await session.find_one(contract_table, Query(target, projection, Unordered())) == ScalarValuesResult(
                number=expected.number, enabled=expected.enabled,
            )


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


@pytest.mark.parametrize("number", [-(2**63) - 1, 2**63])
@pytest.mark.asyncio
async def test_upsert_outside_signed_64_bit_range_preserves_existing_row(
    database: Database, number: int,
) -> None:
    contract_table = scalar_table()
    original = ScalarRow(record_id="existing", number=7, enabled=True, optional_text="original")
    invalid = ScalarRow(
        record_id=original.record_id, number=number, enabled=False, optional_text="replacement",
    )
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=original))

    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        with pytest.raises(
            TypeError,
            match=r"Invalid value for scalar_samples\.number: expected signed 64-bit integer",
        ):
            await session.upsert(
                contract_table,
                UpsertCommand(key=ScalarKey(record_id=original.record_id), row=invalid),
            )

    async with database.read_session() as session:
        observed = await session.find_many(
            contract_table, Query(NoFilter(), AllFields(), Unordered()),
        )
    assert tuple(observed) == (original,)
