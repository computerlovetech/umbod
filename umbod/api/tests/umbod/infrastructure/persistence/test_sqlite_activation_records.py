from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
    CAPABILITY_ACTIVATION_STATE_TABLE,
    CapabilityActivationStateKey,
    CapabilityActivationStateRecord,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Equals,
    InsertCommand,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


@pytest.mark.asyncio
async def test_sqlite_activation_records_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "activation.sqlite3"
    initial = CapabilityActivationStateRecord(
        connector_kind="native", connector_id="target", capability_kind="tool",
        capability_key='shared 雪 "quoted" \\path', status="enabled",
        updated_at="2026-01-02T03:04:05.123456+00:00",
    )
    neighbors = (
        initial.model_copy(update={"capability_kind": "prompt"}),
        initial.model_copy(update={"capability_kind": "resource_template", "status": "disabled"}),
        initial.model_copy(update={"connector_kind": "mcp"}),
        initial.model_copy(update={"connector_kind": "openapi", "status": "disabled"}),
        initial.model_copy(update={"connector_id": "neighbor"}),
        initial.model_copy(update={"capability_key": "other-key"}),
    )
    updated = initial.model_copy(update={
        "status": "disabled", "updated_at": "2026-02-03T04:05:06.654321+00:00",
    })
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            for row in (initial, *neighbors):
                assert await session.insert(CAPABILITY_ACTIVATION_STATE_TABLE, InsertCommand(row=row))
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(
                CAPABILITY_ACTIVATION_STATE_TABLE,
                UpsertCommand(
                    key=CapabilityActivationStateKey(
                        connector_kind=updated.connector_kind, connector_id=updated.connector_id,
                        capability_kind=updated.capability_kind, capability_key=updated.capability_key,
                    ),
                    row=updated,
                ),
            )
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        async with reader.database.read_session() as session:
            for expected in (updated, *neighbors):
                restored = await session.find_many(
                    CAPABILITY_ACTIVATION_STATE_TABLE,
                    Query(AllOf((
                        Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, expected.connector_kind),
                        Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, expected.connector_id),
                        Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND, expected.capability_kind),
                        Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY, expected.capability_key),
                    )), AllFields(), Unordered()),
                )
                assert restored == (expected,)
                assert isinstance(restored[0], CapabilityActivationStateRecord)
    finally:
        await reader.shutdown()

    with closing(sqlite3.connect(path)) as connection, connection:
        raw_rows = connection.execute(
            "SELECT connector_kind, connector_id, capability_kind, capability_key, status, "
            "updated_at, typeof(connector_kind), typeof(connector_id), typeof(capability_kind), "
            "typeof(capability_key), typeof(status), typeof(updated_at) "
            "FROM capability_activation_states"
        ).fetchall()
        columns = connection.execute("PRAGMA table_info(capability_activation_states)").fetchall()
    assert set(raw_rows) == {
        (row.connector_kind, row.connector_id, row.capability_kind, row.capability_key,
         row.status, row.updated_at, "text", "text", "text", "text", "text", "text")
        for row in (updated, *neighbors)
    }
    assert {row[1]: row[2] for row in columns} == {
        "connector_kind": "TEXT", "connector_id": "TEXT", "capability_kind": "TEXT",
        "capability_key": "TEXT", "status": "TEXT", "updated_at": "TEXT",
    }
    assert {row[1]: row[5] for row in columns if row[5]} == {
        "connector_kind": 1, "connector_id": 2, "capability_kind": 3, "capability_key": 4,
    }
