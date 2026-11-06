from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_DEFINITION_CONNECTOR_ID,
    CONNECTOR_DEFINITION_PUBLIC_PATH,
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_CONNECTOR_ID,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_CONNECTOR_ID,
    TOOL_CATALOG_TABLE,
    ConnectorDefinitionKey,
    ConnectorDefinitionRecord,
    ConnectorHealthKey,
    ConnectorHealthRecord,
    ToolCatalogKey,
    ToolCatalogRecord,
)
from umbod.core.persistence import (
    AllFields,
    Equals,
    InsertCommand,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


@pytest.mark.asyncio
async def test_sqlite_downstream_catalog_records_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "downstream.sqlite3"
    initial_definition = ConnectorDefinitionRecord(
        connector_id="target", public_path="/initial", capability_description="Initial",
        document={"display_name": "Initial", "endpoint": "https://example.test/mcp"},
    )
    initial_catalog = ToolCatalogRecord(connector_id="target", snapshot={"tools": []})
    initial_health = ConnectorHealthRecord(connector_id="target", document={"healthy": False})
    neighbor_definition = initial_definition.model_copy(update={
        "connector_id": "neighbor", "public_path": "/neighbor",
    })
    neighbor_catalog = initial_catalog.model_copy(update={"connector_id": "neighbor"})
    neighbor_health = initial_health.model_copy(update={"connector_id": "neighbor"})
    nested = {"values": [None, True, False, 42, {"escaped": '雪 café "quoted" \\path\nline'}]}
    updated_definition = ConnectorDefinitionRecord(
        connector_id="target", public_path='/雪/"quoted"\\path',
        capability_description='Updated 雪 "description" \\path\nline',
        document={
            "display_name": "Updated 雪", "endpoint": "https://example.test/mcp",
            "created_at": "2026-01-02T03:04:05.123456+00:00",
            "updated_at": "2026-02-03T04:05:06.654321+00:00", "metadata": nested,
        },
    )
    updated_catalog = ToolCatalogRecord(
        connector_id="target",
        snapshot={
            "discovered_at": "2026-02-03T04:05:06.654321+00:00",
            "tools": [{
                "name": 'tool 雪 "quoted" \\path', "description": None,
                "inputSchema": {
                    "type": "object", "properties": {"limit": {"type": "integer", "minimum": 0}},
                    "required": ["limit"], "additionalProperties": False,
                },
                "outputSchema": {"type": "array", "items": {"type": ["string", "null"]}},
                "annotations": nested,
            }],
        },
    )
    updated_health = ConnectorHealthRecord(
        connector_id="target",
        document={
            "healthy": True, "failures": 2, "last_error": None,
            "checked_at": "2026-02-03T04:05:06.654321+00:00", "details": nested,
        },
    )
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            for definition in (initial_definition, neighbor_definition):
                assert await session.insert(CONNECTOR_DEFINITION_TABLE, InsertCommand(row=definition))
            for catalog in (initial_catalog, neighbor_catalog):
                assert await session.insert(TOOL_CATALOG_TABLE, InsertCommand(row=catalog))
            for health in (initial_health, neighbor_health):
                assert await session.insert(CONNECTOR_HEALTH_TABLE, InsertCommand(row=health))
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(CONNECTOR_DEFINITION_TABLE, UpsertCommand(
                key=ConnectorDefinitionKey(connector_id="target"), row=updated_definition,
            ))
            await session.upsert(TOOL_CATALOG_TABLE, UpsertCommand(
                key=ToolCatalogKey(connector_id="target"), row=updated_catalog,
            ))
            await session.upsert(CONNECTOR_HEALTH_TABLE, UpsertCommand(
                key=ConnectorHealthKey(connector_id="target"), row=updated_health,
            ))
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        async with reader.database.read_session() as session:
            for expected_definition in (updated_definition, neighbor_definition):
                assert await session.find_many(
                    CONNECTOR_DEFINITION_TABLE,
                    Query(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, expected_definition.connector_id),
                          AllFields(), Unordered()),
                ) == (expected_definition,)
                assert await session.find_many(
                    CONNECTOR_DEFINITION_TABLE,
                    Query(Equals(CONNECTOR_DEFINITION_PUBLIC_PATH, expected_definition.public_path),
                          AllFields(), Unordered()),
                ) == (expected_definition,)
            for expected_catalog in (updated_catalog, neighbor_catalog):
                assert await session.find_many(
                    TOOL_CATALOG_TABLE,
                    Query(Equals(TOOL_CATALOG_CONNECTOR_ID, expected_catalog.connector_id),
                          AllFields(), Unordered()),
                ) == (expected_catalog,)
            for expected_health in (updated_health, neighbor_health):
                assert await session.find_many(
                    CONNECTOR_HEALTH_TABLE,
                    Query(Equals(CONNECTOR_HEALTH_CONNECTOR_ID, expected_health.connector_id),
                          AllFields(), Unordered()),
                ) == (expected_health,)
    finally:
        await reader.shutdown()

    with closing(sqlite3.connect(path)) as connection, connection:
        raw_definitions = connection.execute(
            "SELECT connector_id, document, public_path, capability_description, "
            "typeof(document), typeof(public_path), typeof(capability_description) "
            "FROM downstream_mcp_connector_definitions ORDER BY connector_id"
        ).fetchall()
        raw_catalogs = connection.execute(
            "SELECT connector_id, snapshot, typeof(snapshot) "
            "FROM downstream_mcp_tool_catalogs ORDER BY connector_id"
        ).fetchall()
        raw_health = connection.execute(
            "SELECT connector_id, document, typeof(document) "
            "FROM downstream_mcp_connector_health ORDER BY connector_id"
        ).fetchall()
    assert [(row[0], json.loads(row[1]), *row[2:]) for row in raw_definitions] == [
        (row.connector_id, row.document, row.public_path, row.capability_description,
         "text", "text", "text")
        for row in (neighbor_definition, updated_definition)
    ]
    assert [(row[0], json.loads(row[1]), row[2]) for row in raw_catalogs] == [
        (row.connector_id, row.snapshot, "text") for row in (neighbor_catalog, updated_catalog)
    ]
    assert [(row[0], json.loads(row[1]), row[2]) for row in raw_health] == [
        (row.connector_id, row.document, "text") for row in (neighbor_health, updated_health)
    ]
