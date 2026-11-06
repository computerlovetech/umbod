from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_schema import (
    PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID,
    PERSONAL_OAUTH_ATTEMPT_ID,
    PERSONAL_OAUTH_ATTEMPT_NAMESPACE,
    PERSONAL_OAUTH_ATTEMPT_SUBJECT,
    PERSONAL_OAUTH_ATTEMPT_TABLE,
    PersonalOAuthAttemptKey,
    PersonalOAuthAttemptRecord,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Equals,
    InsertCommand,
    NoFilter,
    OrderBy,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


SECRET = "personal-oauth-physical-record-key"
INITIAL_JSON = (
    r'{"status":"preparing","provider_context":{"opaque":"initial-provider-78e1"},'
    r'"state":"initial-state-29d4","pkce":"initial-pkce-31a6",'
    r'"label":"雪 café","escaped":"\"quoted\"\\path\nline",'
    r'"timestamp":"2026-01-02T03:04:05.123456+00:00"}'
)
NEIGHBOR_JSON = (
    r'{"status":"pending","provider_context":{"opaque":"neighbor-provider-48b2"},'
    r'"state":"neighbor-state-82c7","pkce":"neighbor-pkce-93f1",'
    r'"label":"隣 ☃","escaped":"\\neighbor\tpath\nline",'
    r'"timestamp":"2026-02-03T04:05:06.234567+00:00"}'
)
PENDING_JSON = (
    r'{"status":"pending","provider_context":{"opaque":"pending-provider-17c8"},'
    r'"state":"pending-state-63a5","pkce":"pending-pkce-44e9",'
    r'"label":"更新 café","escaped":"\"pending\"\\path\tline",'
    r'"timestamp":"2026-03-04T05:06:07.345678+00:00"}'
)
EXCHANGING_JSON = (
    r'{"status":"exchanging","provider_context":{"opaque":"exchanging-provider-56f3"},'
    r'"state":"exchanging-state-72b4","pkce":"exchanging-pkce-91d2",'
    r'"claim_id":"exchanging-claim-38a7","label":"交換 ☃",'
    r'"escaped":"\"exchanging\"\\path\nline",'
    r'"timestamp":"2026-04-05T06:07:08.456789+00:00"}'
)
PRIVATE_CANARIES = (
    "initial-provider-78e1", "initial-state-29d4", "initial-pkce-31a6",
    "neighbor-provider-48b2", "neighbor-state-82c7", "neighbor-pkce-93f1",
    "pending-provider-17c8", "pending-state-63a5", "pending-pkce-44e9",
    "exchanging-provider-56f3", "exchanging-state-72b4", "exchanging-pkce-91d2",
    "exchanging-claim-38a7",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updated_document",
    [
        pytest.param(PENDING_JSON, id="pending"),
        pytest.param(EXCHANGING_JSON, id="exchanging"),
    ],
)
async def test_sqlite_personal_oauth_record_updates_survive_runtime_recreation(
    tmp_path: Path, updated_document: str,
) -> None:
    path = tmp_path / "personal-oauth.sqlite3"
    cipher = AuthenticatedTextCipher(SECRET)
    initial = PersonalOAuthAttemptRecord(
        attempt_id="target-attempt", namespace="trusted", subject="target-owner",
        connector_id="shared-connector", document=cipher.encrypt(INITIAL_JSON),
    )
    neighbor = PersonalOAuthAttemptRecord(
        attempt_id="neighbor-attempt", namespace="trusted", subject="neighbor-owner",
        connector_id="shared-connector", document=cipher.encrypt(NEIGHBOR_JSON),
    )
    updated = PersonalOAuthAttemptRecord(
        attempt_id=initial.attempt_id, namespace=initial.namespace, subject=initial.subject,
        connector_id=initial.connector_id, document=cipher.encrypt(updated_document),
    )
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            assert await session.insert(PERSONAL_OAUTH_ATTEMPT_TABLE, InsertCommand(row=initial))
            assert await session.insert(PERSONAL_OAUTH_ATTEMPT_TABLE, InsertCommand(row=neighbor))
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(
                PERSONAL_OAUTH_ATTEMPT_TABLE,
                UpsertCommand(key=PersonalOAuthAttemptKey(attempt_id=initial.attempt_id), row=updated),
            )
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        async with reader.database.read_session() as session:
            restored = await session.find_many(
                PERSONAL_OAUTH_ATTEMPT_TABLE,
                Query(NoFilter(), AllFields(), OrderBy((PERSONAL_OAUTH_ATTEMPT_ID,))),
            )
            indexed_records = await session.find_many(
                PERSONAL_OAUTH_ATTEMPT_TABLE,
                Query(
                    AllOf((
                        Equals(PERSONAL_OAUTH_ATTEMPT_NAMESPACE, updated.namespace),
                        Equals(PERSONAL_OAUTH_ATTEMPT_SUBJECT, updated.subject),
                        Equals(PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID, updated.connector_id),
                    )),
                    AllFields(), Unordered(),
                ),
            )
    finally:
        await reader.shutdown()
    assert restored == (neighbor, updated)
    assert indexed_records == (updated,)
    fresh_cipher = AuthenticatedTextCipher(SECRET)
    assert fresh_cipher.decrypt(restored[0].document) == NEIGHBOR_JSON
    assert fresh_cipher.decrypt(restored[1].document) == updated_document

    with closing(sqlite3.connect(path)) as connection, connection:
        raw_records = connection.execute(
            "SELECT attempt_id, namespace, subject, connector_id, document, typeof(document) "
            "FROM downstream_mcp_personal_oauth_attempts ORDER BY attempt_id"
        ).fetchall()
    assert raw_records == [
        (record.attempt_id, record.namespace, record.subject, record.connector_id,
         record.document, "text")
        for record in (neighbor, updated)
    ]
    database_bytes = path.read_bytes()
    for canary in PRIVATE_CANARIES:
        assert all(canary not in row[4] for row in raw_records)
        assert canary.encode() not in database_bytes
