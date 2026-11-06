import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

import aiosqlite
import pytest
from messaging.models import MessagingEvent

from umbod.core.messaging import DatabaseEventStream
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database
from umbod.infrastructure.persistence.sqlite.schema_preparation import SQLiteCurrentSchemaPreparation


async def _prepared_database(path: Path) -> SQLiteDatabase:
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    await SQLiteCurrentSchemaPreparation(database).execute()
    return database


@pytest.mark.asyncio
async def test_empty_sqlite_database_gets_current_schema_and_indexes(tmp_path: Path) -> None:
    path = tmp_path / "schema.sqlite3"
    database = await _prepared_database(path)
    await DatabaseEventStream(database).append(
        MessagingEvent(event_type="connector.configuration.changed", subject="stored")
    )
    async with aiosqlite.connect(path) as connection:
        table_cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        table_names = {str(row[0]) for row in await table_cursor.fetchall()}
        await table_cursor.close()
        event_index_cursor = await connection.execute("PRAGMA index_list('messaging_events')")
        event_indexes = {str(row[1]) for row in await event_index_cursor.fetchall()}
        await event_index_cursor.close()
        definition_index_cursor = await connection.execute(
            "PRAGMA index_list('downstream_mcp_connector_definitions')"
        )
        definition_indexes = {str(row[1]) for row in await definition_index_cursor.fetchall()}
        await definition_index_cursor.close()
    assert "openapi_connector_catalogs" not in table_names
    assert "messaging_events_type_sequence_idx" in event_indexes
    assert "downstream_mcp_connector_definitions_public_path_uq" in definition_indexes


@pytest.mark.asyncio
async def test_current_schema_preparation_is_safe_during_concurrent_startup(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.sqlite3"
    first = SQLiteCurrentSchemaPreparation(create_unpooled_sqlite_database(str(path), create_parent_dirs=True))
    second = SQLiteCurrentSchemaPreparation(create_unpooled_sqlite_database(str(path), create_parent_dirs=True))
    await asyncio.gather(first.execute(), second.execute())


@pytest.mark.asyncio
async def test_description_override_schema_initializes_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "descriptions.sqlite"
    database = await _prepared_database(path)
    await SQLiteCurrentSchemaPreparation(database).execute()
    with closing(sqlite3.connect(path)) as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'connector_capability_description_overrides'"
        ).fetchone()[0]
        assert "CHECK" in sql
        assert connection.execute('SELECT count(*) FROM connector_capability_description_overrides').fetchone()[0] == 0


@pytest.mark.parametrize(
    "kind,state,description,revision",
    [
        ("unknown", "system", None, 1),
        ("native", "unknown", None, 1),
        ("native", "system", None, 0),
        ("native", "system", None, -1),
        ("native", "system", "unexpected", 1),
        ("native", "overridden", None, 1),
        ("native", "overridden", "", 1),
        ("native", "overridden", "   ", 1),
        ("native", "overridden", "a" * 301, 1),
    ],
)
@pytest.mark.asyncio
async def test_description_override_schema_rejects_invalid_states(
    tmp_path: Path, kind: str, state: str, description: Optional[str], revision: int,
) -> None:
    path = tmp_path / "invalid-descriptions.sqlite"
    await _prepared_database(path)
    statement = (
        "INSERT INTO connector_capability_description_overrides "
        "(connector_id, connector_kind, state, description, revision) VALUES (?, ?, ?, ?, ?)"
    )
    valid = [("system", "native", "system", None, 1), ("overridden", "openapi", "overridden", "a" * 300, 2)]
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.executemany(statement, valid)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            connection.execute(statement, ("invalid", kind, state, description, revision))
        stored = connection.execute(
            "SELECT connector_id, connector_kind, state, description, revision "
            "FROM connector_capability_description_overrides ORDER BY revision"
        ).fetchall()
    assert stored == valid
