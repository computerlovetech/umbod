import asyncio
from pathlib import Path

import aiosqlite
import pytest
from messaging.models import MessagingEvent

from umbod.core.messaging import DatabaseEventStream
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.schema_preparation import SQLiteCurrentSchemaPreparation


async def _prepared_database(path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(str(path), create_parent_dirs=True)
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
    first = SQLiteCurrentSchemaPreparation(SQLiteDatabase(str(path), create_parent_dirs=True))
    second = SQLiteCurrentSchemaPreparation(SQLiteDatabase(str(path), create_parent_dirs=True))
    await asyncio.gather(first.execute(), second.execute())
