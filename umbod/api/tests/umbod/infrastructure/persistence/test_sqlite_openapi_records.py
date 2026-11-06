from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.core.connectors.openapi.models import (
    OpenApiEndpointCapability,
    OpenApiMetadata,
    OpenApiParameter,
    PrimitiveSchema,
)
from umbod.core.connectors.openapi.stores.schema import (
    CATALOG_OPERATION_CATALOG_ID,
    CATALOG_OPERATION_CONNECTOR_ID,
    CATALOG_OPERATION_OPERATION_ID,
    CATALOG_OPERATION_TABLE,
    CATALOG_SOURCE_CATALOG_ID,
    CATALOG_SOURCE_CONNECTOR_ID,
    CATALOG_SOURCE_TABLE,
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_CATALOG_ID,
    CURRENT_CATALOG_HEADER_CONNECTOR_ID,
    CURRENT_CATALOG_HEADER_TABLE,
    CatalogOperationRecord,
    CatalogSourceRecord,
    ConnectorRecord,
    CurrentCatalogHeaderRecord,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Equals,
    InsertCommand,
    NoFilter,
    Query,
    TransactionMode,
    Unordered,
)


@pytest.mark.asyncio
async def test_sqlite_openapi_records_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "openapi.sqlite3"
    document = (
        r'{"display_name":"雪 café","description":"\"quoted\"\\path\nline",'
        r'"created_at":"2026-01-02T03:04:05.123456+00:00",'
        r'"updated_at":"2026-02-03T04:05:06.654321+00:00"}'
    )
    source_document = {
        "openapi": "3.1.0",
        "upload_body": "upload-body-canary-71d3 雪",
        "nested": {"values": [None, True, False, 42, {"escaped": '"quoted"\\path\nline'}]},
    }
    connector = ConnectorRecord(connector_id="target", document=document)
    neighbor_connector = ConnectorRecord(connector_id="neighbor", document='{"display_name":"Other"}')
    header = CurrentCatalogHeaderRecord(
        connector_id="target", catalog_id="catalog",
        metadata=OpenApiMetadata(title="雪 API", version="1.2.3", description='API "description"'),
        server_candidates=("https://z.example/api", "https://a.example/api"),
        approved_hosts=("z.example", "a.example"),
        selected_server_url="https://a.example/api",
        operation_ids=("z-operation", "a-operation"),
        imported_at="2026-02-03T04:05:06.654321+00:00",
    )
    neighbor_header = header.model_copy(update={
        "connector_id": "neighbor", "selected_server_url": "https://z.example/api",
    })
    source = CatalogSourceRecord(
        connector_id="target", catalog_id="catalog", document=source_document,
    )
    sources = (
        source,
        source.model_copy(update={"catalog_id": "other-catalog", "document": {"neighbor": 1}}),
        source.model_copy(update={"connector_id": "neighbor", "document": {"neighbor": 2}}),
    )
    operations = tuple(
        CatalogOperationRecord(
            connector_id="target", catalog_id="catalog", operation_id=operation_id,
            method="get", path="/items", summary="Items 雪", description='Read "items"\nline',
            tags=("z-tag", "a-tag"),
            capability=OpenApiEndpointCapability(
                operation_id=operation_id, method="get", path="/items",
                summary="Items 雪", description='Read "items"\nline',
                parameters=(OpenApiParameter(
                    name="limit", location="query", required=False, description="Maximum items",
                    style="form", explode=True,
                    capability_schema=PrimitiveSchema(
                        type="integer", format="int32", description="Limit", enum=(2, 1),
                    ),
                ),),
                request_bodies=(), response_bodies=(),
            ),
        )
        for operation_id in header.operation_ids
    )
    operation_neighbors = (
        operations[0].model_copy(update={"catalog_id": "other-catalog", "summary": "Other catalog"}),
        operations[0].model_copy(update={"connector_id": "neighbor", "summary": "Other connector"}),
    )
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            for row in (connector, neighbor_connector):
                assert await session.insert(CONNECTOR_TABLE, InsertCommand(row=row))
            for row in (header, neighbor_header):
                assert await session.insert(CURRENT_CATALOG_HEADER_TABLE, InsertCommand(row=row))
            for row in sources:
                assert await session.insert(CATALOG_SOURCE_TABLE, InsertCommand(row=row))
            for row in (*operations, *operation_neighbors):
                assert await session.insert(CATALOG_OPERATION_TABLE, InsertCommand(row=row))
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        async with reader.database.read_session() as session:
            restored_connectors = await session.find_many(
                CONNECTOR_TABLE, Query(NoFilter(), AllFields(), Unordered()),
            )
            assert set(restored_connectors) == {connector, neighbor_connector}
            for expected_header in (header, neighbor_header):
                assert await session.find_many(
                    CURRENT_CATALOG_HEADER_TABLE,
                    Query(AllOf((
                        Equals(CURRENT_CATALOG_HEADER_CONNECTOR_ID, expected_header.connector_id),
                        Equals(CURRENT_CATALOG_HEADER_CATALOG_ID, expected_header.catalog_id),
                    )), AllFields(), Unordered()),
                ) == (expected_header,)
            for expected_source in sources:
                assert await session.find_many(
                    CATALOG_SOURCE_TABLE,
                    Query(AllOf((
                        Equals(CATALOG_SOURCE_CONNECTOR_ID, expected_source.connector_id),
                        Equals(CATALOG_SOURCE_CATALOG_ID, expected_source.catalog_id),
                    )), AllFields(), Unordered()),
                ) == (expected_source,)
            for expected_operation in (*operations, *operation_neighbors):
                assert await session.find_many(
                    CATALOG_OPERATION_TABLE,
                    Query(AllOf((
                        Equals(CATALOG_OPERATION_CONNECTOR_ID, expected_operation.connector_id),
                        Equals(CATALOG_OPERATION_CATALOG_ID, expected_operation.catalog_id),
                        Equals(CATALOG_OPERATION_OPERATION_ID, expected_operation.operation_id),
                    )), AllFields(), Unordered()),
                ) == (expected_operation,)
    finally:
        await reader.shutdown()

    with closing(sqlite3.connect(path)) as connection, connection:
        raw_connector = connection.execute(
            "SELECT document, typeof(document) FROM openapi_connectors WHERE connector_id = ?",
            ("target",),
        ).fetchone()
        raw_header = connection.execute(
            "SELECT metadata, server_candidates, approved_hosts, operation_ids, imported_at, "
            "selected_server_url, typeof(metadata), typeof(server_candidates), "
            "typeof(approved_hosts), typeof(operation_ids) FROM openapi_current_catalog_headers "
            "WHERE connector_id = ? AND catalog_id = ?", ("target", "catalog"),
        ).fetchone()
        raw_source = connection.execute(
            "SELECT document, typeof(document) FROM openapi_catalog_sources "
            "WHERE connector_id = ? AND catalog_id = ?", ("target", "catalog"),
        ).fetchone()
        raw_operations = connection.execute(
            "SELECT operation_id, tags, capability, typeof(tags), typeof(capability) "
            "FROM openapi_catalog_operations WHERE connector_id = ? AND catalog_id = ?",
            ("target", "catalog"),
        ).fetchall()
        source_columns = connection.execute("PRAGMA table_info(openapi_catalog_sources)").fetchall()
        operation_columns = connection.execute("PRAGMA table_info(openapi_catalog_operations)").fetchall()
    assert raw_connector == (document, "text")
    assert json.loads(raw_connector[0]) == json.loads(document)
    assert json.loads(raw_header[0]) == header.metadata.model_dump(mode="json")
    assert json.loads(raw_header[1]) == ["https://z.example/api", "https://a.example/api"]
    assert json.loads(raw_header[2]) == ["z.example", "a.example"]
    assert json.loads(raw_header[3]) == ["z-operation", "a-operation"]
    assert raw_header[4:] == (
        "2026-02-03T04:05:06.654321+00:00", "https://a.example/api",
        "text", "text", "text", "text",
    )
    assert raw_source[1] == "text"
    assert "upload-body-canary-71d3" in raw_source[0]
    assert json.loads(raw_source[0]) == source_document
    assert {row[0] for row in raw_operations} == {"z-operation", "a-operation"}
    raw_by_operation = {row[0]: row for row in raw_operations}
    for operation in operations:
        raw_operation = raw_by_operation[operation.operation_id]
        assert json.loads(raw_operation[1]) == ["z-tag", "a-tag"]
        assert json.loads(raw_operation[2]) == operation.capability.model_dump(mode="json")
        assert raw_operation[3:] == ("text", "text")
    assert {row[1]: row[5] for row in source_columns if row[5]} == {
        "connector_id": 1, "catalog_id": 2,
    }
    assert {row[1]: row[5] for row in operation_columns if row[5]} == {
        "connector_id": 1, "catalog_id": 2, "operation_id": 3,
    }
