import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from tests.umbod.core.persistence.contract_support import (
    GeneratedKey,
    GeneratedRow,
    generated_table,
    non_reusing_generated_table,
)
from umbod.core.messaging.stores.schema import (
    EVENT_SEQUENCE,
    EVENT_TABLE,
    MessagingEventRecord,
)
from umbod.core.persistence import (
    DeleteQuery,
    GeneratedIntegerKeyInsertCommand,
    InsertCommand,
    NoFilter,
    TransactionMode,
    UpsertCommand,
)
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_operation", ("generated", "insert", "upsert"))
async def test_non_reusing_key_preserves_deleted_watermark_after_schema_checks_and_restart(
    tmp_path: Path, seed_operation: str
) -> None:
    path = tmp_path / "keys.sqlite3"
    table, sequence = non_reusing_generated_table("generated_records")
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=False)
    await database.ensure_schema((table,))
    seed = GeneratedRow(sequence=9000, payload="deleted")
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        if seed_operation == "generated":
            maximum = await session.insert_generated_integer_key(
                table, GeneratedIntegerKeyInsertCommand(seed, sequence)
            )
        elif seed_operation == "insert":
            assert await session.insert(table, InsertCommand(row=seed))
            maximum = seed.sequence
        else:
            await session.upsert(
                table, UpsertCommand(key=GeneratedKey(sequence=seed.sequence), row=seed)
            )
            maximum = seed.sequence
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.delete(table, DeleteQuery(NoFilter())) == 1
    await database.ensure_schema((table,))
    await database.ensure_schema((table,))
    restarted = create_unpooled_sqlite_database(str(path), create_parent_dirs=False)
    await restarted.ensure_schema((table,))
    async with restarted.session(mode=TransactionMode.READ_WRITE) as session:
        appended = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="next"), sequence),
        )
    assert appended > maximum


@pytest.mark.asyncio
async def test_ordinary_integer_key_schema_does_not_enable_autoincrement(tmp_path: Path) -> None:
    path = tmp_path / "ordinary.sqlite3"
    table, _ = generated_table("ordinary_records")
    await create_unpooled_sqlite_database(str(path), create_parent_dirs=False).ensure_schema((table,))
    with closing(sqlite3.connect(path)) as connection, connection:
        definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'ordinary_records'"
        ).fetchone()
    assert definition is not None
    assert "AUTOINCREMENT" not in definition[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "definition",
    (
        "sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL",
        "sequence INTEGER PRIMARY KEY /* AUTOINCREMENT */, payload TEXT NOT NULL",
        "sequence INTEGER PRIMARY KEY -- AUTOINCREMENT\n, payload TEXT NOT NULL",
        "sequence INTEGER PRIMARY KEY -- comment\r AUTOINCREMENT\n, payload TEXT NOT NULL",
        "sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL DEFAULT 'AUTOINCREMENT'",
        'sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL, "AUTOINCREMENT" TEXT',
        "sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL, `AUTOINCREMENT` TEXT",
        "sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL, [AUTOINCREMENT] TEXT",
        "sequence INTEGER, payload TEXT NOT NULL, other INTEGER PRIMARY KEY AUTOINCREMENT",
    ),
)
async def test_incompatible_schema_requires_migration_without_changing_rows_or_indexes(
    tmp_path: Path, definition: str
) -> None:
    path = tmp_path / "legacy.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(f"CREATE TABLE legacy_records ({definition})")
        connection.execute("CREATE INDEX legacy_payload_idx ON legacy_records(payload)")
        connection.execute("INSERT INTO legacy_records(sequence, payload) VALUES (71, 'original')")
    table, _ = non_reusing_generated_table("legacy_records")
    preceding, _ = non_reusing_generated_table("must_rollback")
    with pytest.raises(ValueError, match="legacy_records.*explicit migration"):
        await create_unpooled_sqlite_database(str(path), create_parent_dirs=False).ensure_schema((preceding, table))
    with closing(sqlite3.connect(path)) as connection, connection:
        rows = connection.execute("SELECT sequence, payload FROM legacy_records").fetchall()
        indexes = connection.execute("PRAGMA index_list(legacy_records)").fetchall()
        rolled_back = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'must_rollback'"
        ).fetchone()
    assert rows == [(71, "original")]
    assert any(index[1] == "legacy_payload_idx" for index in indexes)
    assert rolled_back is None


@pytest.mark.asyncio
async def test_runtime_readiness_rejects_plain_legacy_event_table_without_data_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy_events.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "CREATE TABLE messaging_events "
            "(sequence INTEGER PRIMARY KEY, event_type TEXT NOT NULL, document TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO messaging_events VALUES (42, 'opaque', 'original')")
    runtime = create_sqlite_runtime(path)
    try:
        with pytest.raises(ValueError, match="messaging_events.*explicit migration"):
            await runtime.readiness.ensure_ready()
    finally:
        await runtime.shutdown()
    with closing(sqlite3.connect(path)) as connection, connection:
        rows = connection.execute("SELECT * FROM messaging_events").fetchall()
    assert rows == [(42, "opaque", "original")]


@pytest.mark.asyncio
async def test_runtime_readiness_preserves_existing_event_autoincrement_history_after_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "existing_events.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "CREATE TABLE messaging_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "event_type TEXT NOT NULL, document TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO messaging_events VALUES (9000, 'opaque', 'deleted')")
        connection.execute("DELETE FROM messaging_events")
    runtime = create_sqlite_runtime(path)
    try:
        await runtime.readiness.ensure_ready()
    finally:
        await runtime.shutdown()
    restarted = create_sqlite_runtime(path)
    try:
        await restarted.readiness.ensure_ready()
        async with restarted.database.session(mode=TransactionMode.READ_WRITE) as session:
            sequence = await session.insert_generated_integer_key(
                EVENT_TABLE,
                GeneratedIntegerKeyInsertCommand(
                    MessagingEventRecord(sequence=0, event_type="opaque", document="next"),
                    EVENT_SEQUENCE,
                ),
            )
    finally:
        await restarted.shutdown()
    assert sequence > 9000
