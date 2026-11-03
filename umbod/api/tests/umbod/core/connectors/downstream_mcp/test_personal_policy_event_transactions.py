import sqlite3
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.connectors.downstream_mcp.models import DiscoveredTool, DiscoveredToolWithoutOutputSchema, OAuthConnectorDefinition, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolPolicyStore, ReplacePersonalToolPolicy
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, SaveConnectorDefinition, ToolCatalogFound, create_downstream_mcp_stores
from umbod.core.messaging.stores.event_stream import DatabaseEventStream


def _tool(name: str) -> DiscoveredTool:
    return DiscoveredToolWithoutOutputSchema(
        identity=ToolIdentity(connector_id="personal", downstream_name=name),
        title="Private metadata", description="Private administrator description",
        input_schema={"type": "object"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ("connector.configuration.changed", "connector.capability_activation.changed"))
async def test_policy_event_append_failure_restores_policy_catalog_and_events(tmp_path: Path, event_type: str) -> None:
    path = tmp_path / "personal-policy.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    stores = await create_downstream_mcp_stores("test-secret", runtime.database)
    await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="personal", display_name="Personal", endpoint_url="https://personal.test/mcp",
        authorization_mode="personal",
    )))
    policy_store: PersonalToolPolicyStore = stores.personal_tool_policies
    original = await policy_store.replace(ReplacePersonalToolPolicy(
        connector_id="personal", expected_revision="unconfigured", tools=(_tool("old"),), native_identities=(),
    ))
    events = DatabaseEventStream(runtime.database)
    previous_events = await events.list_after(0, 100)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_policy_event BEFORE INSERT ON messaging_events "
            f"WHEN NEW.event_type = '{event_type}' BEGIN SELECT RAISE(ABORT, 'event append failed'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        await policy_store.replace(ReplacePersonalToolPolicy(
            connector_id="personal", expected_revision=original.policy.revision,
            tools=(_tool("new"),), native_identities=(),
        ))
    assert await policy_store.get(ConnectorIdQuery(connector_id="personal")) == original.policy
    catalog = await stores.catalogs.get(ConnectorIdQuery(connector_id="personal"))
    assert isinstance(catalog, ToolCatalogFound)
    assert catalog.snapshot.tools == original.policy.tools
    assert await events.list_after(0, 100) == previous_events


@pytest.mark.asyncio
async def test_policy_replace_publishes_sanitized_events_once_and_noop_publishes_nothing(tmp_path: Path) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "personal-policy.sqlite3")
    stores = await create_downstream_mcp_stores("test-secret", runtime.database)
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
    events = await DatabaseEventStream(runtime.database).list_after(0, 100)
    assert [entry.event.event_type for entry in events] == [
        "connector.configuration.changed", "connector.capability_activation.changed",
    ]
    assert events[1].event.metadata == {
        "connector_kind": "downstream_mcp", "connector_id": "personal",
        "capability_kind": "tool", "capability_key": "read",
    }
    assert "Private" not in str(events)
