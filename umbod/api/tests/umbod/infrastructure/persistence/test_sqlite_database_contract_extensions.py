import sqlite3
from contextlib import closing

from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database
from pathlib import Path
import pytest
from umbod.core.persistence import AllFields, Equals, Fields, GeneratedIntegerKeyInsertCommand, InsertCommand, NoFilter, PersistenceDecodingError, Query, TransactionMode, Unordered, UpsertCommand
from tests.umbod.core.persistence.contract_support import CanonicalKey, CanonicalRow, GeneratedRow, SampleDocument, SampleKey, ScalarKey, ScalarRow, ScalarValuesResult, canonical_table, generated_table, row, scalar_table, serialized_claim_observations, table

@pytest.mark.asyncio
async def test_sqlite_persists_across_database_instances(tmp_path: Path) -> None:
    path = tmp_path / 'persisted.sqlite'
    (contract_table, _, _, _) = table('persisted_samples')
    writer = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    await writer.ensure_schema((contract_table,))
    async with writer.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=row('persisted')))
    reader = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
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
    writer = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
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

    reader = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
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
    database = create_unpooled_sqlite_database(str(tmp_path / 'reserved.sqlite'), create_parent_dirs=True)
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.insert(contract_table, InsertCommand(row=row('record'))) is True


@pytest.mark.asyncio
async def test_sqlite_serializes_read_check_upsert_claims_across_database_instances(tmp_path: Path) -> None:
    path = tmp_path / "shared-claims.sqlite"
    first = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    second = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    assert await serialized_claim_observations(first, second) == ("available", "claimed")


@pytest.mark.asyncio
async def test_sqlite_serialized_session_acquires_writer_lock_before_any_read(tmp_path: Path) -> None:
    path = tmp_path / "immediate-lock.sqlite"
    contract_table, _, _, _ = table("locked_records")
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE):
        with closing(sqlite3.connect(path, timeout=0)) as contender:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                contender.execute("BEGIN IMMEDIATE")


@pytest.mark.asyncio
async def test_sqlite_json_fields_store_canonical_text(tmp_path: Path) -> None:
    path = tmp_path / "canonical.sqlite"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    contract_table = canonical_table()
    await database.ensure_schema((contract_table,))
    value = CanonicalRow(
        record_id="record", enabled=True,
        payload={"z": [1, {"b": False, "a": None}], "a": "value"},
        labels=("beta", "alpha"), document=SampleDocument(label="document"),
    )
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=value))
    with closing(sqlite3.connect(path)) as connection:
        stored = connection.execute(
            'SELECT payload, labels, document FROM canonical_samples WHERE record_id = ?',
            (value.record_id,),
        ).fetchall()
    assert stored == [(
        '{"a":"value","z":[1,{"a":null,"b":false}]}',
        '["beta","alpha"]',
        '{"label":"document"}',
    )]


@pytest.mark.asyncio
async def test_sqlite_trigger_error_rolls_back_preceding_mutations_across_tables(tmp_path: Path) -> None:
    path = tmp_path / "trigger-rollback.sqlite"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    first, _, _, _ = table("first_records")
    second, _, _, _ = table("second_records")
    await database.ensure_schema((first, second))
    original = row("existing", "original")
    key = SampleKey(owner_id=original.owner_id, record_id=original.record_id)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for contract_table in (first, second):
            await session.insert(contract_table, InsertCommand(row=original))
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                "CREATE TRIGGER reject_update BEFORE UPDATE ON second_records "
                "BEGIN SELECT RAISE(ABORT, 'rejected'); END"
            )
    with pytest.raises(sqlite3.IntegrityError, match="rejected"):
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(first, UpsertCommand(key=key, row=row("existing", "changed")))
            await session.insert(second, InsertCommand(row=row("new", "uncommitted")))
            await session.upsert(second, UpsertCommand(key=key, row=row("existing", "rejected")))
    reader = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    async with reader.read_session() as session:
        assert await session.find_many(first, Query(NoFilter(), AllFields(), Unordered())) == (original,)
        assert await session.find_many(second, Query(NoFilter(), AllFields(), Unordered())) == (original,)


@pytest.mark.parametrize(
    "field_name,corrupt_value",
    [
        ("payload", "not-json"),
        ("labels", "not-json"),
        ("document", "not-json"),
        ("labels", "{}"),
        ("document", "{}"),
    ],
)
@pytest.mark.asyncio
async def test_sqlite_decodes_only_projected_json_fields_and_reports_corruption_context(
    tmp_path: Path, field_name: str, corrupt_value: str,
) -> None:
    path = tmp_path / "corrupt-json.sqlite"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    contract_table = canonical_table()
    await database.ensure_schema((contract_table,))
    value = CanonicalRow(
        record_id="record", enabled=True, payload={"active": True},
        labels=("label",), document=SampleDocument(label="document"),
    )
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=value))
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                f'UPDATE canonical_samples SET "{field_name}" = ? WHERE record_id = ?',
                (corrupt_value, value.record_id),
            )
    target = Equals(contract_table.key_codec.fields[0], value.record_id)
    projected = Query(target, Fields(CanonicalKey, contract_table.key_codec.fields), Unordered())
    async with database.read_session() as session:
        assert await session.find_one(contract_table, projected) == CanonicalKey(record_id=value.record_id)
        assert await session.find_many(contract_table, projected) == (CanonicalKey(record_id=value.record_id),)
        for read in (session.find_one, session.find_many):
            with pytest.raises(PersistenceDecodingError) as failure:
                await read(contract_table, Query(target, AllFields(), Unordered()))
            assert failure.value.table_name == contract_table.name
            assert failure.value.field_name == field_name
            assert f"{contract_table.name}.{field_name}" in str(failure.value)


@pytest.mark.asyncio
async def test_sqlite_generated_insert_trigger_error_rolls_back_preceding_mutations(tmp_path: Path) -> None:
    path = tmp_path / "generated-trigger.sqlite"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    records, _, _, _ = table("mutable_records")
    generated, sequence = generated_table("generated_records")
    await database.ensure_schema((records, generated))
    original = row("existing", "original")
    key = SampleKey(owner_id=original.owner_id, record_id=original.record_id)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(records, InsertCommand(row=original))
        original_sequence = await session.insert_generated_integer_key(
            generated, GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="original"), sequence),
        )
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                "CREATE TRIGGER reject_generated BEFORE INSERT ON generated_records "
                "BEGIN SELECT RAISE(ABORT, 'generated insert failed'); END"
            )
    with pytest.raises(sqlite3.IntegrityError, match="generated insert failed"):
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(records, UpsertCommand(key=key, row=row("existing", "changed")))
            await session.insert(records, InsertCommand(row=row("new", "uncommitted")))
            await session.insert_generated_integer_key(
                generated, GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="rejected"), sequence),
            )
    reader = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    async with reader.read_session() as session:
        assert await session.find_many(records, Query(NoFilter(), AllFields(), Unordered())) == (original,)
        assert await session.find_many(generated, Query(NoFilter(), AllFields(), Unordered())) == (
            GeneratedRow(sequence=original_sequence, payload="original"),
        )


@pytest.mark.asyncio
async def test_sqlite_later_generated_insert_trigger_error_rolls_back_earlier_generated_insert(tmp_path: Path) -> None:
    path = tmp_path / "later-generated-trigger.sqlite"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    records, _, _, _ = table("mutable_records")
    generated, sequence = generated_table("generated_records")
    await database.ensure_schema((records, generated))
    original = row("existing", "original")
    key = SampleKey(owner_id=original.owner_id, record_id=original.record_id)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(records, InsertCommand(row=original))
        original_sequence = await session.insert_generated_integer_key(
            generated, GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="original"), sequence),
        )
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                "CREATE TRIGGER reject_later_generated BEFORE INSERT ON generated_records "
                "WHEN NEW.payload = 'rejected' "
                "BEGIN SELECT RAISE(ABORT, 'later generated insert failed'); END"
            )
    successful_sequences: list[int] = []
    with pytest.raises(sqlite3.IntegrityError, match="later generated insert failed"):
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(records, UpsertCommand(key=key, row=row("existing", "changed")))
            await session.insert(records, InsertCommand(row=row("new", "uncommitted")))
            successful_sequences.append(await session.insert_generated_integer_key(
                generated, GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="accepted"), sequence),
            ))
            await session.insert_generated_integer_key(
                generated, GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="rejected"), sequence),
            )
    assert len(successful_sequences) == 1
    reader = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    async with reader.read_session() as session:
        assert await session.find_many(records, Query(NoFilter(), AllFields(), Unordered())) == (original,)
        assert await session.find_many(generated, Query(NoFilter(), AllFields(), Unordered())) == (
            GeneratedRow(sequence=original_sequence, payload="original"),
        )
