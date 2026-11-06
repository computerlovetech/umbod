from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import Mock

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.messaging.stores.schema import EVENT_TABLE, MessagingEventKey, MessagingEventRecord
from umbod.core.persistence import Database, DatabaseSession, GeneratedIntegerKeyInsertCommand, Table, TransactionMode
from umbod.core.connectors.downstream_mcp.models import DiscoveredTool, DiscoveredToolWithoutOutputSchema, OAuthConnectorDefinition, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolPolicyStore, ReplacePersonalToolPolicy
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, SaveConnectorDefinition, ToolCatalogFound, create_downstream_mcp_stores
from umbod.core.messaging.stores.event_stream import DatabaseEventStream


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


def _tool(name: str) -> DiscoveredTool:
    return DiscoveredToolWithoutOutputSchema(
        identity=ToolIdentity(connector_id="personal", downstream_name=name),
        title="Private metadata", description="Private administrator description",
        input_schema={"type": "object"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ("connector.configuration.changed", "connector.capability_activation.changed"))
async def test_policy_event_append_failure_restores_policy_catalog_and_events(database: Database, event_type: str) -> None:
    stores = await create_downstream_mcp_stores("test-secret", database)
    await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="personal", display_name="Personal", endpoint_url="https://personal.test/mcp",
        authorization_mode="personal",
    )))
    policy_store: PersonalToolPolicyStore = stores.personal_tool_policies
    original = await policy_store.replace(ReplacePersonalToolPolicy(
        connector_id="personal", expected_revision="unconfigured", tools=(_tool("old"),), native_identities=(),
    ))
    events = DatabaseEventStream(database)
    previous_events = await events.list_after(0, 100)
    successful_events: list[str] = []

    @asynccontextmanager
    async def rejecting_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with database.session(mode=mode) as session:
            async def insert_event(
                table: Table[MessagingEventRecord, MessagingEventKey],
                command: GeneratedIntegerKeyInsertCommand[MessagingEventRecord],
            ) -> int:
                if table == EVENT_TABLE and command.row.event_type == event_type:
                    raise RuntimeError("event append failed")
                sequence = await session.insert_generated_integer_key(table, command)
                if table == EVENT_TABLE:
                    successful_events.append(command.row.event_type)
                return sequence

            rejecting = Mock(spec=DatabaseSession, wraps=session)
            rejecting.insert_generated_integer_key.side_effect = insert_event
            yield rejecting

    rejecting_database = Mock(spec=Database, wraps=database)
    rejecting_database.session.side_effect = rejecting_session
    rejecting_stores = await create_downstream_mcp_stores("test-secret", rejecting_database)
    with pytest.raises(RuntimeError, match="event append failed"):
        await rejecting_stores.personal_tool_policies.replace(ReplacePersonalToolPolicy(
            connector_id="personal", expected_revision=original.policy.revision,
            tools=(_tool("new"),), native_identities=(),
        ))
    assert successful_events == ([] if event_type == "connector.configuration.changed" else ["connector.configuration.changed"])
    assert await policy_store.get(ConnectorIdQuery(connector_id="personal")) == original.policy
    catalog = await stores.catalogs.get(ConnectorIdQuery(connector_id="personal"))
    assert isinstance(catalog, ToolCatalogFound)
    assert catalog.snapshot.tools == original.policy.tools
    assert await events.list_after(0, 100) == previous_events


@pytest.mark.asyncio
async def test_policy_replace_publishes_sanitized_events_once_and_noop_publishes_nothing(database: Database) -> None:
    stores = await create_downstream_mcp_stores("test-secret", database)
    await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="personal", display_name="Personal", endpoint_url="https://personal.test/mcp",
        authorization_mode="personal",
    )))
    policy_store: PersonalToolPolicyStore = stores.personal_tool_policies
    replacement = await policy_store.replace(ReplacePersonalToolPolicy(
        connector_id="personal", expected_revision="unconfigured", tools=(_tool("read"),), native_identities=(),
    ))
    await policy_store.replace(ReplacePersonalToolPolicy(
        connector_id="personal", expected_revision=replacement.policy.revision,
        tools=replacement.policy.tools, native_identities=(),
    ))
    events = await DatabaseEventStream(database).list_after(0, 100)
    assert [entry.event.event_type for entry in events] == [
        "connector.configuration.changed", "connector.capability_activation.changed",
    ]
    assert events[1].event.metadata == {
        "connector_kind": "downstream_mcp", "connector_id": "personal",
        "capability_kind": "tool", "capability_key": "read",
    }
    assert "Private" not in str(events)
