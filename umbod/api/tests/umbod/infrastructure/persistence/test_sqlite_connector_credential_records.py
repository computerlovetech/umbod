import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_CREDENTIAL_CONNECTOR_ID,
    CONNECTOR_CREDENTIAL_TABLE,
    ConnectorCredentialKey,
    ConnectorCredentialRecord,
)
from umbod.core.persistence import (
    AllFields,
    Equals,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


@pytest.mark.asyncio
async def test_encrypted_connector_credential_records_survive_runtime_recreation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "credentials.sqlite3"
    secret = "credential-record-encryption-key"
    document = r'{"bearer_token":"credential-record-secret-canary","label":"雪 café","escaped":"\"quoted\"\\path\nline"}'
    neighbor_document = r'{"bearer_token":"neighbor-credential-secret-canary"}'
    cipher = AuthenticatedTextCipher(secret)
    expected = ConnectorCredentialRecord(
        connector_id="alpha", document=cipher.encrypt(document),
    )
    neighbor = ConnectorCredentialRecord(
        connector_id="beta", document=cipher.encrypt(neighbor_document),
    )
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            for record in (expected, neighbor):
                await session.upsert(
                    CONNECTOR_CREDENTIAL_TABLE,
                    UpsertCommand(
                        key=ConnectorCredentialKey(connector_id=record.connector_id),
                        row=record,
                    ),
                )
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        async with reader.database.read_session() as session:
            restored = await session.find_one(
                CONNECTOR_CREDENTIAL_TABLE,
                Query(
                    Equals(CONNECTOR_CREDENTIAL_CONNECTOR_ID, expected.connector_id),
                    AllFields(), Unordered(),
                ),
            )
            restored_neighbor = await session.find_one(
                CONNECTOR_CREDENTIAL_TABLE,
                Query(
                    Equals(CONNECTOR_CREDENTIAL_CONNECTOR_ID, neighbor.connector_id),
                    AllFields(), Unordered(),
                ),
            )
    finally:
        await reader.shutdown()
    assert restored is not None
    assert restored_neighbor is not None
    assert restored == expected
    assert restored_neighbor == neighbor
    fresh_cipher = AuthenticatedTextCipher(secret)
    assert fresh_cipher.decrypt(restored.document) == document
    assert fresh_cipher.decrypt(restored_neighbor.document) == neighbor_document

    with closing(sqlite3.connect(path)) as connection, connection:
        raw_records = connection.execute(
            "SELECT connector_id, document, typeof(document) "
            "FROM downstream_mcp_connector_credentials ORDER BY connector_id"
        ).fetchall()
    assert raw_records == [
        (expected.connector_id, expected.document, "text"),
        (neighbor.connector_id, neighbor.document, "text"),
    ]
    database_bytes = path.read_bytes()
    for canary in ("credential-record-secret-canary", "neighbor-credential-secret-canary"):
        assert all(canary not in row[1] for row in raw_records)
        assert canary.encode() not in database_bytes
