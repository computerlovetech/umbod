import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolObservation
from umbod.core.connectors.downstream_mcp.stores.personal_tools_schema import (
    PERSONAL_TOOL_OBSERVATION_SUBJECT, PERSONAL_TOOL_OBSERVATION_TABLE,
    PersonalToolObservationRecord, PersonalToolObservationRecordKey,
)
from umbod.core.persistence import AllFields, NoFilter, OrderBy, Query, TransactionMode, UpsertCommand
from tests.persistence_runtime import prepared_sqlite_runtime


@pytest.mark.asyncio
async def test_encrypted_personal_tool_observation_updates_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "observations.sqlite"
    secret = "observation-test-key"
    cipher = AuthenticatedTextCipher(secret)
    owner = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="owner"), connector_id="personal")
    tool = DiscoveredToolWithoutOutputSchema(
        identity=ToolIdentity(connector_id="personal", downstream_name="read"),
        title="Résumé", description="initial-private-observation-canary",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
    )
    initial = PersonalToolObservation(
        version=2, key=owner, authorization_revision="auth-1", configuration_revision="config-1",
        inventory_revision="inventory-1", tools=(tool,),
        expires_at=datetime(2026, 1, 1, 12, 30, 1, 123456, tzinfo=timezone.utc),
    )
    updated = initial.model_copy(update={
        "authorization_revision": "auth-2", "configuration_revision": "config-2", "inventory_revision": "inventory-2",
        "tools": (tool.model_copy(update={"description": "updated-private-observation-canary", "input_schema": {"type": "object"}}),),
        "expires_at": initial.expires_at + timedelta(minutes=1),
    })
    neighbor = initial.model_copy(update={
        "key": PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="other"), connector_id="personal"),
    })
    key = PersonalToolObservationRecordKey(namespace=owner.principal.namespace, subject=owner.principal.subject, connector_id=owner.connector_id)
    neighbor_key = PersonalToolObservationRecordKey(namespace=neighbor.key.principal.namespace, subject=neighbor.key.principal.subject, connector_id=neighbor.key.connector_id)
    initial_record = PersonalToolObservationRecord(**key.model_dump(), document=cipher.encrypt(initial.model_dump_json()))
    updated_record = PersonalToolObservationRecord(**key.model_dump(), document=cipher.encrypt(updated.model_dump_json()))
    neighbor_record = PersonalToolObservationRecord(**neighbor_key.model_dump(), document=cipher.encrypt(neighbor.model_dump_json()))
    runtime = await prepared_sqlite_runtime(path)
    try:
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(PERSONAL_TOOL_OBSERVATION_TABLE, UpsertCommand(key=key, row=initial_record))
            await session.upsert(PERSONAL_TOOL_OBSERVATION_TABLE, UpsertCommand(key=neighbor_key, row=neighbor_record))
        async with runtime.database.read_session() as session:
            assert await session.find_many(PERSONAL_TOOL_OBSERVATION_TABLE, Query(NoFilter(), AllFields(), OrderBy((PERSONAL_TOOL_OBSERVATION_SUBJECT,)))) == (neighbor_record, initial_record)
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(PERSONAL_TOOL_OBSERVATION_TABLE, UpsertCommand(key=key, row=updated_record))
    finally:
        await runtime.shutdown()
    with closing(sqlite3.connect(path)) as connection:
        documents = connection.execute("SELECT document FROM downstream_mcp_personal_tool_observations").fetchall()
    for canary in ("initial-private-observation-canary", "updated-private-observation-canary"):
        assert all(canary not in document for document, in documents)
        assert canary.encode() not in path.read_bytes()
    reopened = await prepared_sqlite_runtime(path)
    try:
        async with reopened.database.read_session() as session:
            restored = await session.find_many(PERSONAL_TOOL_OBSERVATION_TABLE, Query(NoFilter(), AllFields(), OrderBy((PERSONAL_TOOL_OBSERVATION_SUBJECT,))))
        assert restored == (neighbor_record, updated_record)
        reopened_cipher = AuthenticatedTextCipher(secret)
        assert tuple(PersonalToolObservation.model_validate_json(reopened_cipher.decrypt(record.document)) for record in restored) == (neighbor, updated)
    finally:
        await reopened.shutdown()
