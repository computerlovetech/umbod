from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.core.capabilities.descriptions.stores.schema import (
    CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
    CapabilityDescriptionOverrideKey,
    CapabilityDescriptionOverrideRecord,
)
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.configuration.persistence.stores.schema import (
    CONNECTOR_CONFIGURATION_TABLE,
    ConnectorConfigurationKey,
    ConnectorConfigurationRecord,
)
from umbod.core.invocation.policy_store import (
    CONNECTOR_INVOCATION_POLICY_TABLE,
    ConnectorInvocationPolicyRow,
    ConnectorInvocationPolicyRowKey,
)
from umbod.core.messaging.stores.schema import (
    EVENT_SEQUENCE,
    EVENT_TABLE,
    MessagingEventRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DatabaseSession,
    GeneratedIntegerKeyInsertCommand,
    InsertCommand,
    NoFilter,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


Records = tuple[
    ConnectorConfigurationRecord,
    ConnectorInvocationPolicyRow,
    CapabilityDescriptionOverrideRecord,
]
StoredRecords = tuple[
    set[ConnectorConfigurationRecord],
    set[ConnectorInvocationPolicyRow],
    set[CapabilityDescriptionOverrideRecord],
]
SECRET = "physical-record-test-encryption-key"
INITIAL_JSON = r'{"secret":"initial-canary-71d3","label":"雪 café","escaped":"\"quoted\"\\path\nline"}'
UPDATED_JSON = r'{"secret":"updated-canary-95b7","label":"雪 ☃","escaped":"\\new\tpath\nline"}'


def _initial_records(connector_id: str) -> Records:
    return (
        ConnectorConfigurationRecord(
            connector_id=connector_id,
            ciphertext=AuthenticatedTextCipher(SECRET).encrypt(INITIAL_JSON),
            updated_at="2026-01-02T03:04:05.123456+00:00",
        ),
        ConnectorInvocationPolicyRow(
            connector_kind="openapi", connector_id=connector_id,
            operation_name="shared-operation", mode="ask", revision=1,
        ),
        CapabilityDescriptionOverrideRecord(
            connector_id=connector_id, connector_kind="openapi", state="overridden",
            description='Initial 雪\n"quoted" \\path', revision=1,
        ),
    )


async def _insert_records(session: DatabaseSession, records: Records) -> tuple[bool, bool, bool]:
    configuration, policy, description = records
    return (
        await session.insert(CONNECTOR_CONFIGURATION_TABLE, InsertCommand(row=configuration)),
        await session.insert(CONNECTOR_INVOCATION_POLICY_TABLE, InsertCommand(row=policy)),
        await session.insert(CAPABILITY_DESCRIPTION_OVERRIDE_TABLE, InsertCommand(row=description)),
    )


async def _upsert_records(session: DatabaseSession, records: Records) -> None:
    configuration, policy, description = records
    await session.upsert(
        CONNECTOR_CONFIGURATION_TABLE,
        UpsertCommand(
            key=ConnectorConfigurationKey(connector_id=configuration.connector_id),
            row=configuration,
        ),
    )
    await session.upsert(
        CONNECTOR_INVOCATION_POLICY_TABLE,
        UpsertCommand(
            key=ConnectorInvocationPolicyRowKey(
                connector_kind=policy.connector_kind, connector_id=policy.connector_id,
                operation_name=policy.operation_name,
            ),
            row=policy,
        ),
    )
    await session.upsert(
        CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
        UpsertCommand(
            key=CapabilityDescriptionOverrideKey(connector_id=description.connector_id),
            row=description,
        ),
    )


async def _read_records(database: Database) -> StoredRecords:
    async with database.read_session() as session:
        configurations = await session.find_many(
            CONNECTOR_CONFIGURATION_TABLE, Query(NoFilter(), AllFields(), Unordered()),
        )
        policies = await session.find_many(
            CONNECTOR_INVOCATION_POLICY_TABLE, Query(NoFilter(), AllFields(), Unordered()),
        )
        descriptions = await session.find_many(
            CAPABILITY_DESCRIPTION_OVERRIDE_TABLE, Query(NoFilter(), AllFields(), Unordered()),
        )
    return set(configurations), set(policies), set(descriptions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,description",
    [("overridden", 'Updated 雪\n"quoted" \\path\t☃'), ("system", "")],
)
async def test_sqlite_configuration_record_updates_survive_runtime_recreation(
    tmp_path: Path, state: str, description: str,
) -> None:
    path = tmp_path / "configuration.sqlite3"
    initial = _initial_records("target")
    neighbor = _initial_records("neighbor")
    updated = (
        initial[0].model_copy(update={
            "ciphertext": AuthenticatedTextCipher(SECRET).encrypt(UPDATED_JSON),
            "updated_at": "2026-02-03T04:05:06.654321+00:00",
        }),
        initial[1].model_copy(update={"mode": "direct", "revision": 2}),
        initial[2].model_copy(update={"state": state, "description": description, "revision": 2}),
    )
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            assert await _insert_records(session, initial) == (True, True, True)
            assert await _insert_records(session, neighbor) == (True, True, True)
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await _upsert_records(session, updated)
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        restored = await _read_records(reader.database)
    finally:
        await reader.shutdown()
    assert restored == (
        {updated[0], neighbor[0]}, {updated[1], neighbor[1]}, {updated[2], neighbor[2]},
    )
    restored_configurations = {row.connector_id: row for row in restored[0]}
    cipher = AuthenticatedTextCipher(SECRET)
    assert cipher.decrypt(restored_configurations["target"].ciphertext) == UPDATED_JSON
    assert cipher.decrypt(restored_configurations["neighbor"].ciphertext) == INITIAL_JSON

    with closing(sqlite3.connect(path)) as connection, connection:
        raw_configurations = connection.execute(
            "SELECT connector_id, ciphertext, typeof(ciphertext), updated_at "
            "FROM connector_configurations ORDER BY connector_id"
        ).fetchall()
        raw_policies = connection.execute(
            "SELECT connector_id, connector_kind, operation_name, mode, revision, typeof(revision) "
            "FROM connector_invocation_policies ORDER BY connector_id"
        ).fetchall()
        raw_descriptions = connection.execute(
            "SELECT connector_id, connector_kind, state, description, typeof(description), "
            "revision, typeof(revision) FROM connector_capability_description_overrides "
            "ORDER BY connector_id"
        ).fetchall()
    assert raw_configurations == [
        (row.connector_id, row.ciphertext, "text", row.updated_at)
        for row in (neighbor[0], updated[0])
    ]
    assert raw_policies == [
        (row.connector_id, row.connector_kind, row.operation_name, row.mode, row.revision, "integer")
        for row in (neighbor[1], updated[1])
    ]
    assert raw_descriptions == [
        (neighbor[2].connector_id, "openapi", "overridden", neighbor[2].description, "text", 1, "integer"),
        ("target", "openapi", state, description if state == "overridden" else None,
         "text" if state == "overridden" else "null", 2, "integer"),
    ]
    database_bytes = path.read_bytes()
    for canary in ("initial-canary-71d3", "updated-canary-95b7"):
        assert all(canary not in row[1] for row in raw_configurations)
        assert canary.encode() not in database_bytes


@pytest.mark.asyncio
async def test_sqlite_late_event_insert_failure_rolls_back_configuration_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollback.sqlite3"
    initial = _initial_records("target")
    updated = (
        initial[0].model_copy(update={
            "ciphertext": AuthenticatedTextCipher(SECRET).encrypt(UPDATED_JSON),
            "updated_at": "2026-02-03T04:05:06.654321+00:00",
        }),
        initial[1].model_copy(update={"mode": "direct", "revision": 2}),
        initial[2].model_copy(update={"description": "Updated 雪", "revision": 2}),
    )
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            assert await _insert_records(session, initial) == (True, True, True)
            original_sequence = await session.insert_generated_integer_key(
                EVENT_TABLE,
                GeneratedIntegerKeyInsertCommand(
                    MessagingEventRecord(sequence=0, event_type="opaque", document="original"),
                    EVENT_SEQUENCE,
                ),
            )
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER reject_event_document BEFORE INSERT ON messaging_events "
                "WHEN NEW.document = 'rejected' "
                "BEGIN SELECT RAISE(ABORT, 'rejected document'); END"
            )
        with pytest.raises(sqlite3.IntegrityError, match="rejected document"):
            async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                await _upsert_records(session, updated)
                accepted_sequence = await session.insert_generated_integer_key(
                    EVENT_TABLE,
                    GeneratedIntegerKeyInsertCommand(
                        MessagingEventRecord(sequence=0, event_type="opaque", document="accepted"),
                        EVENT_SEQUENCE,
                    ),
                )
                assert accepted_sequence > original_sequence
                await session.insert_generated_integer_key(
                    EVENT_TABLE,
                    GeneratedIntegerKeyInsertCommand(
                        MessagingEventRecord(sequence=0, event_type="opaque", document="rejected"),
                        EVENT_SEQUENCE,
                    ),
                )
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        restored = await _read_records(reader.database)
        async with reader.database.read_session() as session:
            events = await session.find_many(
                EVENT_TABLE, Query(NoFilter(), AllFields(), Unordered()),
            )
    finally:
        await reader.shutdown()
    assert restored == ({initial[0]}, {initial[1]}, {initial[2]})
    assert set(events) == {
        MessagingEventRecord(sequence=original_sequence, event_type="opaque", document="original"),
    }
