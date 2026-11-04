import sqlite3
from contextlib import closing

from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from pathlib import Path
import pytest
from umbod.core.persistence import AllFields, Equals, Fields, InsertCommand, NoFilter, Query, TransactionMode, Unordered, UpsertCommand
from tests.umbod.core.persistence.contract_support import ScalarKey, ScalarRow, ScalarValuesResult, row, scalar_table, serialized_claim_observations, table

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

@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.asyncio
async def test_sqlite_scalar_upsert_projection_persists_across_database_instances(
    tmp_path: Path, enabled: bool,
) -> None:
    path = tmp_path / "scalar-upserts.sqlite"
    contract_table = scalar_table()
    writer = SQLiteDatabase(str(path), create_parent_dirs=True)
    await writer.ensure_schema((contract_table,))
    initial = ScalarRow(
        record_id="updated", number=7, enabled=enabled, optional_text="2026-01-01T00:00:00+00:00",
    )
    updated = initial.model_copy(update={
        "number": 42, "enabled": not enabled, "optional_text": "2026-01-02T00:00:00+00:00",
    })
    key = ScalarKey(record_id=initial.record_id)
    for value in (initial, updated):
        async with writer.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(contract_table, UpsertCommand(key=key, row=value))

    with closing(sqlite3.connect(path)) as connection:
        stored = connection.execute(
            'SELECT number, enabled, optional_text, typeof(number), typeof(enabled), typeof(optional_text) '
            'FROM scalar_samples WHERE record_id = ?',
            (updated.record_id,),
        ).fetchall()
    assert stored == [(updated.number, int(updated.enabled), updated.optional_text, "integer", "integer", "text")]

    reader = SQLiteDatabase(str(path), create_parent_dirs=True)
    target = Equals(contract_table.key_codec.fields[0], initial.record_id)
    projection = Fields(ScalarValuesResult, contract_table.row_codec.fields[1:3])
    async with reader.read_session() as session:
        assert await session.find_many(contract_table, Query(NoFilter(), AllFields(), Unordered())) == (updated,)
        assert await session.find_one(contract_table, Query(target, projection, Unordered())) == ScalarValuesResult(
            number=updated.number, enabled=updated.enabled,
        )


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
