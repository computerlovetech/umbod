from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from umbod.core.messaging.stores.schema import (
    CHECKPOINT_CONSUMER_ID,
    CHECKPOINT_TABLE,
    EVENT_SEQUENCE,
    EVENT_TABLE,
    MessagingCheckpointKey,
    MessagingCheckpointRecord,
    MessagingEventRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DeleteQuery,
    Equals,
    GeneratedIntegerKeyInsertCommand,
    NoFilter,
    OrderBy,
    Query,
    TransactionMode,
    UpsertCommand,
)
from tests.persistence_runtime import create_sqlite_runtime, prepared_inmemory_runtime, prepared_sqlite_runtime


@pytest_asyncio.fixture(params=("inmemory", "sqlite"))
async def database(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Database]:
    if request.param == "inmemory":
        runtime = await prepared_inmemory_runtime()
    else:
        runtime = await prepared_sqlite_runtime(tmp_path / "messaging.sqlite3")
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


async def _insert_and_delete_maximum(database: Database) -> tuple[int, int, int]:
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        first = await session.insert_generated_integer_key(
            EVENT_TABLE,
            GeneratedIntegerKeyInsertCommand(
                MessagingEventRecord(sequence=0, event_type="opaque", document="original"),
                EVENT_SEQUENCE,
            ),
        )
        deleted = await session.insert_generated_integer_key(
            EVENT_TABLE,
            GeneratedIntegerKeyInsertCommand(
                MessagingEventRecord(sequence=0, event_type="opaque", document="deleted"),
                EVENT_SEQUENCE,
            ),
        )
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        deleted_count = await session.delete(EVENT_TABLE, DeleteQuery(Equals(EVENT_SEQUENCE, deleted)))
    return first, deleted, deleted_count


async def _append_and_read(database: Database) -> tuple[int, tuple[MessagingEventRecord, ...]]:
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        appended = await session.insert_generated_integer_key(
            EVENT_TABLE,
            GeneratedIntegerKeyInsertCommand(
                MessagingEventRecord(sequence=0, event_type="opaque", document="appended"),
                EVENT_SEQUENCE,
            ),
        )
    async with database.read_session() as session:
        stored = await session.find_many(
            EVENT_TABLE, Query(NoFilter(), AllFields(), OrderBy((EVENT_SEQUENCE,)))
        )
    return appended, tuple(stored)


@pytest.mark.asyncio
async def test_event_schema_does_not_reuse_deleted_committed_maximum(database: Database) -> None:
    first, deleted, deleted_count = await _insert_and_delete_maximum(database)
    appended, stored = await _append_and_read(database)
    assert (first, deleted, deleted_count) == (1, 2, 1)
    assert appended == deleted + 1
    assert stored == (
        MessagingEventRecord(sequence=first, event_type="opaque", document="original"),
        MessagingEventRecord(sequence=appended, event_type="opaque", document="appended"),
    )


@pytest.mark.asyncio
async def test_sqlite_event_schema_does_not_reuse_deleted_maximum_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "messaging.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    try:
        first, deleted, deleted_count = await _insert_and_delete_maximum(runtime.database)
    finally:
        await runtime.shutdown()
    restarted_runtime = await prepared_sqlite_runtime(path)
    try:
        appended, stored = await _append_and_read(restarted_runtime.database)
    finally:
        await restarted_runtime.shutdown()
    assert (first, deleted, deleted_count) == (1, 2, 1)
    assert appended == deleted + 1
    assert stored == (
        MessagingEventRecord(sequence=first, event_type="opaque", document="original"),
        MessagingEventRecord(sequence=appended, event_type="opaque", document="appended"),
    )


@pytest.mark.asyncio
async def test_sqlite_event_document_text_survives_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "event-document.sqlite3"
    document = (
        '{\n'
        r'  "metadata": {"label": "雪 café", "escaped": "\"quoted\"\\path\nline"},'
        '\n  "subject": "connector:test"\n}'
    )
    event_type = "connector.publication.changed"
    runtime = create_sqlite_runtime(path)
    try:
        await runtime.readiness.ensure_ready()
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            sequence = await session.insert_generated_integer_key(
                EVENT_TABLE,
                GeneratedIntegerKeyInsertCommand(
                    MessagingEventRecord(sequence=0, event_type=event_type, document=document),
                    EVENT_SEQUENCE,
                ),
            )
    finally:
        await runtime.shutdown()
    reader_runtime = create_sqlite_runtime(path)
    try:
        await reader_runtime.readiness.ensure_ready()
        async with reader_runtime.database.read_session() as session:
            stored = await session.find_one(
                EVENT_TABLE,
                Query(Equals(EVENT_SEQUENCE, sequence), AllFields(), OrderBy((EVENT_SEQUENCE,))),
            )
    finally:
        await reader_runtime.shutdown()
    assert sequence == 1
    assert stored == MessagingEventRecord(sequence=sequence, event_type=event_type, document=document)


@pytest.mark.asyncio
async def test_checkpoint_schema_upserts_integer_sequence_across_database_instances(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoints.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    try:
        for sequence in (7, 7, 9):
            async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                await session.upsert(
                    CHECKPOINT_TABLE,
                    UpsertCommand(
                        key=MessagingCheckpointKey(consumer_id="consumer"),
                        row=MessagingCheckpointRecord(consumer_id="consumer", sequence=sequence),
                    ),
                )
    finally:
        await runtime.shutdown()
    reader_runtime = await prepared_sqlite_runtime(path)
    try:
        async with reader_runtime.database.read_session() as session:
            stored = await session.find_one(
                CHECKPOINT_TABLE,
                Query(
                    Equals(CHECKPOINT_CONSUMER_ID, "consumer"),
                    AllFields(),
                    OrderBy((CHECKPOINT_CONSUMER_ID,)),
                ),
            )
    finally:
        await reader_runtime.shutdown()
    assert stored == MessagingCheckpointRecord(consumer_id="consumer", sequence=9)
    assert stored is not None
    assert type(stored.sequence) is int
