from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import pytest
import pytest_asyncio
from pydantic import BaseModel

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.umbod.rest.user_catalogue.query_budget_support import (
    CountingDatabase,
    CountingSession,
    QueryCounts,
)
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_TABLE,
    CapabilityActivationStateRecord,
)
from umbod.core.admin_overview.models import Available, ConnectorCounts, ToolCounts
from umbod.core.configuration.persistence.stores.schema import (
    CONNECTOR_CONFIGURATION_TABLE,
    ConnectorConfigurationRecord,
)
from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredToolWithoutOutputSchema,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_TABLE,
    ConnectorDefinitionRecord,
    ConnectorHealthRecord,
    ToolCatalogRecord,
)
from umbod.core.connectors.native.registry import ConnectorRegistry, InMemoryConnectorRegistry
from umbod.core.connectors.openapi.models import OpenApiMetadata
from umbod.core.connectors.openapi.stores.schema import (
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_TABLE,
    ConnectorRecord,
    CurrentCatalogHeaderRecord,
)
from umbod.core.groups.stores.schema import GROUP_TABLE, PermissionGroupRecord
from umbod.core.persistence import Database, DatabaseSession, InsertCommand, Query, Table, TransactionMode
from umbod.core.persistence.query import AllOf, AnyOf, Equals, Fields, OneOf
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE, PublicationStateRecord
from umbod.proxies import Model
from umbod.rest.admin_overview.reader import DatabaseOverviewReader

pytestmark = pytest.mark.asyncio
RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class EmptyConfiguration(Model):
    pass


class OverviewQueryCounts(QueryCounts):
    def __init__(self) -> None:
        super().__init__()
        self.observations: list[tuple[str, object, tuple[BaseModel, ...]]] = []
        self.fail_table = ""

    def reset(self) -> None:
        super().reset()
        self.observations.clear()


class OverviewCountingSession(CountingSession):
    def __init__(self, session: DatabaseSession, counts: OverviewQueryCounts) -> None:
        super().__init__(session, counts)
        self.overview_counts = counts

    async def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT],
    ) -> Sequence[ResultT]:
        projections = {
            "connector_configurations": {"connector_id"},
            "openapi_connectors": {"connector_id"},
            "openapi_current_catalog_headers": {"connector_id", "operation_ids"},
            "downstream_mcp_connector_definitions": {"connector_id", "document"},
            "mcp_permission_groups": {"group_id"},
            "capability_activation_states": {"connector_kind", "connector_id", "capability_key"},
        }
        allowed = set(projections) | {
            "downstream_mcp_tool_catalogs", "downstream_mcp_connector_health",
            "connector_publication_states", "capability_activation_states",
        }
        assert table.name in allowed, table.name
        if table.name in projections:
            assert isinstance(query.projection, Fields)
            assert {field.name for field in query.projection.fields} == projections[table.name]
        if isinstance(query.filter, OneOf):
            assert len(query.filter.values) <= 200
        if table.name == self.overview_counts.fail_table:
            raise RuntimeError("Dependent overview read failed")
        rows = await super().find_many(table, query)
        if table.name == "capability_activation_states":
            scopes = activation_query_scopes(query.filter)
            assert all(row.connector_id in scopes[row.connector_kind] for row in rows)
        self.overview_counts.observations.append((table.name, query.filter, tuple(rows)))
        return rows


def activation_query_scopes(predicate: object) -> dict[str, tuple[str, ...]]:
    assert isinstance(predicate, AllOf)
    assert len(predicate.predicates) == 3
    capability, status, scoped = predicate.predicates
    assert isinstance(capability, Equals)
    assert capability.field.name == "capability_kind" and capability.value == "tool"
    assert isinstance(status, Equals)
    assert status.field.name == "status" and status.value == "enabled"
    assert isinstance(scoped, AnyOf)
    scopes: dict[str, tuple[str, ...]] = {}
    for branch in scoped.predicates:
        assert isinstance(branch, AllOf)
        kind, identifiers = branch.predicates
        assert isinstance(kind, Equals) and kind.field.name == "connector_kind"
        assert isinstance(identifiers, OneOf) and identifiers.field.name == "connector_id"
        scopes[kind.value] = identifiers.values
    assert len({identifier for identifiers in scopes.values() for identifier in identifiers}) <= 200
    return scopes


class OverviewCountingDatabase(CountingDatabase):
    def __init__(self, database: Database, counts: OverviewQueryCounts) -> None:
        super().__init__(database, counts)
        self.overview_counts = counts

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        self.counts.sessions += 1
        async with self.database.session(mode=mode) as session:
            yield OverviewCountingSession(session, self.overview_counts)


@pytest_asyncio.fixture(params=["inmemory", "sqlite"])
async def database(
    request: pytest.FixtureRequest, tmp_path: Path,
) -> AsyncIterator[tuple[Database, OverviewQueryCounts]]:
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "overview.sqlite")
    )
    counts = OverviewQueryCounts()
    try:
        yield OverviewCountingDatabase(runtime.database, counts), counts
    finally:
        await runtime.shutdown()


def registry(connector_ids: tuple[str, ...], tool_count: int) -> ConnectorRegistry:
    return InMemoryConnectorRegistry(
        [
            {
                "id": connector_id, "display_name": connector_id, "description": connector_id,
                "capability_description": "Connector capabilities",
                "extension": {"source": "built-in"},
                "configuration_schema": EmptyConfiguration,
                "tool_descriptions": [
                    {"operation_name": f"tool_{index}", "description": "Tool"}
                    for index in range(tool_count)
                ],
            }
            for connector_id in connector_ids + ("unavailable",)
        ],
        connector_ids,
    )


async def insert(
    session: DatabaseSession, table: Table[RowT, KeyT], row: RowT,
) -> None:
    await session.insert(table, InsertCommand(row=row))


async def seed_shared(
    session: DatabaseSession, connector_id: str, tool_count: int, mode: str,
) -> None:
    await insert(session, CONNECTOR_DEFINITION_TABLE, ConnectorDefinitionRecord(
        connector_id=connector_id, public_path=f"/mcp/proxies/{connector_id}",
        capability_description="Connector capabilities",
        document={
            "connector_id": connector_id, "display_name": connector_id,
            "tool_name_prefix": connector_id, "capability_description": "Connector capabilities",
            "endpoint_url": "https://example.invalid/mcp", "auth_type": "oauth",
            "authorization_mode": mode, "public_path": f"/mcp/proxies/{connector_id}",
        },
    ))
    snapshot = ToolCatalogSnapshot(
        connector_id=connector_id, discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        tools=tuple(DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id=connector_id, downstream_name=f"tool_{index}"),
            title="Tool", description="Tool", input_schema={"type": "object"},
        ) for index in range(tool_count)),
    )
    await insert(session, TOOL_CATALOG_TABLE, ToolCatalogRecord(
        connector_id=connector_id,
        snapshot=snapshot.model_dump(mode="json") if mode == "shared" else {"invalid": True},
    ))
    await insert(session, CONNECTOR_HEALTH_TABLE, ConnectorHealthRecord(
        connector_id=connector_id, document={"status": "unhealthy"},
    ))


async def seed_inventory(database: Database, tool_count: int) -> None:
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await insert(session, CONNECTOR_CONFIGURATION_TABLE, ConnectorConfigurationRecord(
            connector_id="native", ciphertext="not decryptable", updated_at="now",
        ))
        await insert(session, CONNECTOR_TABLE, ConnectorRecord(
            connector_id="openapi", document="not a source document",
        ))
        await insert(session, CURRENT_CATALOG_HEADER_TABLE, CurrentCatalogHeaderRecord(
            connector_id="openapi", catalog_id="current",
            metadata=OpenApiMetadata(title="API", version="1", description="API"),
            server_candidates=(), approved_hosts=(), selected_server_url="https://example.invalid",
            operation_ids=tuple(f"tool_{index}" for index in range(tool_count)), imported_at="now",
        ))
        await seed_shared(session, "shared", tool_count, "shared")
        await seed_shared(session, "personal", tool_count, "personal")
        for connector_id in ("native", "openapi", "shared"):
            await insert(session, PUBLICATION_STATE_TABLE, PublicationStateRecord(
                connector_id=connector_id, published=True, previously_published=True,
                revision=1, updated_at="now",
            ))
            connector_kind = {"native": "native", "openapi": "openapi", "shared": "downstream_mcp"}[connector_id]
            for index in range(tool_count):
                await insert(session, CAPABILITY_ACTIVATION_STATE_TABLE, CapabilityActivationStateRecord(
                    connector_kind=connector_kind, connector_id=connector_id,
                    capability_kind="tool", capability_key=f"tool_{index}",
                    status="enabled", updated_at="now",
                ))
        for connector_kind, capability_kind, key in (
            ("native", "tool", "stale"),
            ("native", "prompt", "tool_0"),
            ("openapi", "tool", "tool_0"),
        ):
            await insert(session, CAPABILITY_ACTIVATION_STATE_TABLE, CapabilityActivationStateRecord(
                connector_kind=connector_kind, connector_id="shared", capability_kind=capability_kind,
                capability_key=key, status="enabled", updated_at="now",
            ))
        for group_id in ("readers", "writers", "", "   "):
            await insert(session, GROUP_TABLE, PermissionGroupRecord(group_id=group_id))


@pytest.mark.parametrize("tool_count", [1, 40, 100])
async def test_fixed_connector_inventory_has_constant_reads_and_one_session(
    database: tuple[Database, QueryCounts], tool_count: int,
) -> None:
    db, counts = database
    await seed_inventory(db, tool_count)
    counts.reset()

    snapshot = await DatabaseOverviewReader(db, registry(("native",), tool_count)).read()

    assert [family.kind for family in snapshot.breakdown] == ["catalog", "openapi", "mcp"]
    for family in snapshot.breakdown:
        assert family.tools == Available(status="available", value=ToolCounts(known=tool_count, enabled=tool_count))
        assert isinstance(family.connectors, Available)
        assert family.connectors.value.configured == 1
        assert family.connectors.value.published == 1
    assert snapshot.breakdown[2].connectors.value.unhealthy == 1
    assert snapshot.permission_groups == Available(status="available", value=2)
    assert counts.sessions == 1
    assert len(counts.reads) == 9
    assert all(count == 1 for count in counts.reads.values())
    assert not counts.writes
    assert counts.schema_calls == 0


async def test_empty_inventory_and_unconfigured_deployment_available_native(
    database: tuple[Database, QueryCounts],
) -> None:
    db, counts = database
    snapshot = await DatabaseOverviewReader(db, registry(("native",), 2)).read()
    assert snapshot.breakdown[0].connectors == Available(status="available", value=ConnectorCounts(
        configured=0, published=0, unconfigured=1, draft=0, unpublished=0, unhealthy=0,
    ))
    assert snapshot.breakdown[0].tools == Available(status="available", value=ToolCounts(known=2, enabled=0))
    for family in snapshot.breakdown[1:]:
        assert family.tools == Available(status="available", value=ToolCounts(known=0, enabled=0))
    assert counts.sessions == 1


async def test_unknown_health_and_missing_catalog_do_not_invent_unhealthy_or_tools(
    database: tuple[Database, QueryCounts],
) -> None:
    db, _ = database
    async with db.session(mode=TransactionMode.READ_WRITE) as session:
        await insert(session, CONNECTOR_DEFINITION_TABLE, ConnectorDefinitionRecord(
            connector_id="shared", public_path="/mcp/proxies/shared", capability_description="Shared capabilities",
            document={
                "connector_id": "shared", "display_name": "Shared", "tool_name_prefix": "Shared",
                "endpoint_url": "https://example.invalid/mcp", "auth_type": "none",
            },
        ))
        await insert(session, CONNECTOR_HEALTH_TABLE, ConnectorHealthRecord(
            connector_id="shared", document={"status": "unknown"},
        ))
    snapshot = await DatabaseOverviewReader(db, registry((), 0)).read()
    assert snapshot.breakdown[2].connectors == Available(status="available", value=ConnectorCounts(
        configured=1, published=0, unconfigured=0, draft=0, unpublished=1, unhealthy=0,
    ))
    assert snapshot.breakdown[2].tools == Available(status="available", value=ToolCounts(known=0, enabled=0))


@pytest.mark.parametrize(
    "published,previous,has_configuration,expected_status",
    [
        (True, False, False, "published"),
        (False, True, False, "unpublished"),
        (False, False, True, "draft"),
        (False, False, False, "unconfigured"),
    ],
)
async def test_publication_precedence_counts_published_and_previously_published_as_configured(
    database: tuple[Database, QueryCounts],
    published: bool, previous: bool, has_configuration: bool, expected_status: str,
) -> None:
    db, _ = database
    async with db.session(mode=TransactionMode.READ_WRITE) as session:
        await insert(session, CONNECTOR_TABLE, ConnectorRecord(connector_id="openapi", document="unused"))
        for connector_id in ("native", "openapi"):
            await insert(session, PUBLICATION_STATE_TABLE, PublicationStateRecord(
                connector_id=connector_id, published=published, previously_published=previous,
                revision=1, updated_at="now",
            ))
        if has_configuration:
            await insert(session, CONNECTOR_CONFIGURATION_TABLE, ConnectorConfigurationRecord(
                connector_id="native", ciphertext="invalid ciphertext", updated_at="now",
            ))
            await insert(session, CURRENT_CATALOG_HEADER_TABLE, CurrentCatalogHeaderRecord(
                connector_id="openapi", catalog_id="current",
                metadata=OpenApiMetadata(title="API", version="1", description="API"),
                server_candidates=(), approved_hosts=(), selected_server_url="", operation_ids=(),
                imported_at="now",
            ))
    snapshot = await DatabaseOverviewReader(db, registry(("native",), 0)).read()
    for family in snapshot.breakdown[:2]:
        assert isinstance(family.connectors, Available)
        actual = family.connectors.value
        assert getattr(actual, expected_status) == 1
        assert actual.configured == int(expected_status != "unconfigured")
        assert sum((actual.published, actual.unpublished, actual.draft, actual.unconfigured)) == 1


async def test_header_and_state_reads_are_bounded_by_connector_batches(
    database: tuple[Database, QueryCounts],
) -> None:
    db, counts = database
    identifiers = tuple(f"connector-{index}" for index in range(201))
    async with db.session(mode=TransactionMode.READ_WRITE) as session:
        for connector_id in identifiers:
            await insert(session, CONNECTOR_TABLE, ConnectorRecord(connector_id=connector_id, document="unused"))
    counts.reset()

    snapshot = await DatabaseOverviewReader(db, registry(identifiers, 0)).read()

    assert snapshot.breakdown[0].connectors.value.unconfigured == 201
    assert snapshot.breakdown[1].connectors.value.unconfigured == 201
    assert counts.reads["openapi_current_catalog_headers"] == 2
    assert counts.reads["connector_configurations"] == 2
    assert counts.reads["connector_publication_states"] == 2
    assert counts.reads["capability_activation_states"] == 2
    assert counts.sessions == 1


async def test_activation_requires_exact_current_tool_and_connector_kind(
    database: tuple[Database, OverviewQueryCounts],
) -> None:
    db, counts = database
    async with db.session(mode=TransactionMode.READ_WRITE) as session:
        for connector_kind, capability_kind, key, status in (
            ("native", "tool", "tool_0", "enabled"),
            ("native", "tool", "tool_1", "disabled"),
            ("native", "tool", "stale", "enabled"),
            ("native", "prompt", "tool_1", "enabled"),
            ("native", "resource", "tool_1", "enabled"),
            ("openapi", "tool", "tool_1", "enabled"),
            ("downstream_mcp", "tool", "tool_1", "enabled"),
        ):
            await insert(session, CAPABILITY_ACTIVATION_STATE_TABLE, CapabilityActivationStateRecord(
                connector_kind=connector_kind, connector_id="native", capability_kind=capability_kind,
                capability_key=key, status=status, updated_at="now",
            ))
    snapshot = await DatabaseOverviewReader(db, registry(("native",), 3)).read()
    assert snapshot.breakdown[0].tools == Available(status="available", value=ToolCounts(known=3, enabled=1))
    activation_reads = [
        (predicate, rows) for table, predicate, rows in counts.observations
        if table == "capability_activation_states"
    ]
    assert len(activation_reads) == 1
    predicate, rows = activation_reads[0]
    assert activation_query_scopes(predicate) == {"native": ("native",)}
    assert {row.model_dump_json() for row in rows} == {
        '{"connector_kind":"native","connector_id":"native","capability_key":"tool_0"}',
        '{"connector_kind":"native","connector_id":"native","capability_key":"stale"}',
    }


async def test_shared_catalog_and_health_reads_batch_only_shared_definitions(
    database: tuple[Database, OverviewQueryCounts],
) -> None:
    db, counts = database
    shared_ids = {f"shared-{index:03d}" for index in range(201)}
    personal_ids = {f"personal-{index:03d}" for index in range(201)}
    async with db.session(mode=TransactionMode.READ_WRITE) as session:
        for connector_id in sorted(shared_ids):
            await seed_shared(session, connector_id, 1, "shared")
        for connector_id in sorted(personal_ids):
            await seed_shared(session, connector_id, 1, "personal")
    counts.reset()

    snapshot = await DatabaseOverviewReader(db, registry((), 0)).read()

    assert snapshot.breakdown[2].connectors.value.configured == 201
    assert snapshot.breakdown[2].connectors.value.unhealthy == 201
    assert snapshot.breakdown[2].tools == Available(status="available", value=ToolCounts(known=201, enabled=0))
    for table_name in ("downstream_mcp_tool_catalogs", "downstream_mcp_connector_health"):
        reads = [(predicate, rows) for table, predicate, rows in counts.observations if table == table_name]
        assert len(reads) == counts.reads[table_name] == 2
        scoped_ids: set[str] = set()
        batch_sizes: list[int] = []
        for predicate, rows in reads:
            assert isinstance(predicate, OneOf)
            scoped_ids.update(predicate.values)
            batch_sizes.append(len(predicate.values))
            assert {row.connector_id for row in rows} == set(predicate.values)
        assert batch_sizes == [200, 1]
        assert scoped_ids == shared_ids
        assert scoped_ids.isdisjoint(personal_ids)
    assert counts.reads["downstream_mcp_connector_definitions"] == 1
    assert counts.reads["capability_activation_states"] == 2
    assert counts.sessions == 1


async def test_dependent_plan_failure_propagates_without_partial_summary(
    database: tuple[Database, OverviewQueryCounts],
) -> None:
    db, counts = database
    await seed_inventory(db, 1)
    counts.reset()
    counts.fail_table = "capability_activation_states"

    with pytest.raises(RuntimeError, match="Dependent overview read failed"):
        await DatabaseOverviewReader(db, registry(("native",), 1)).read()

    completed = {table for table, _, _ in counts.observations}
    assert {
        "openapi_current_catalog_headers", "downstream_mcp_tool_catalogs",
        "downstream_mcp_connector_health", "connector_publication_states",
    } <= completed
    assert counts.sessions == 1
    assert not counts.writes
