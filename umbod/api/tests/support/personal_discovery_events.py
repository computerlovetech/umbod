import pytest

from messaging.models import StreamEvent
from tests.support.messaging import reject_database_event_appends
from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredTool,
    DiscoveredToolWithoutOutputSchema,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores.personal_authorization_health_schema import (
    PERSONAL_AUTHORIZATION_REJECTION_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_schema import (
    PERSONAL_DISCOVERY_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configuration_schema import (
    PERSONAL_OAUTH_CONFIGURATION_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_schema import (
    PERSONAL_OAUTH_ATTEMPT_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_setup_schema import (
    PERSONAL_OAUTH_SETUP_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.personal_refresh_schema import (
    PERSONAL_REFRESH_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.personal_tools_schema import (
    PERSONAL_TOOL_OBSERVATION_TABLE,
    PERSONAL_TOOL_POLICY_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.schema import PERSONAL_CONNECTION_TABLE
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.core.persistence import (
    AllFields,
    Database,
    NoFilter,
    Query,
    TransactionMode,
    Unordered,
)
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE


async def events(database: Database) -> list[StreamEvent]:
    return await DatabaseEventStream(database).list_after(0, 1000)


async def rollback_snapshot(database: Database) -> tuple[object, ...]:
    tables = (
        PERSONAL_OAUTH_SETUP_TABLE,
        PUBLICATION_STATE_TABLE,
        PERSONAL_DISCOVERY_TABLE,
        PERSONAL_CONNECTION_TABLE,
        PERSONAL_AUTHORIZATION_REJECTION_TABLE,
        PERSONAL_REFRESH_TABLE,
        PERSONAL_OAUTH_CONFIGURATION_TABLE,
        PERSONAL_OAUTH_ATTEMPT_TABLE,
        PERSONAL_TOOL_OBSERVATION_TABLE,
        PERSONAL_TOOL_POLICY_TABLE,
    )
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        return tuple(
            [
                tuple(
                    sorted(
                        await session.find_many(
                            table,
                            Query(
                                filter=NoFilter(),
                                projection=AllFields(),
                                ordering=Unordered(),
                            ),
                        ),
                        key=repr,
                    )
                )
                for table in tables
            ]
        )


def reject_events(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    reject_database_event_appends(
        database, monkeypatch, event_types=("connector.discovery.changed",)
    )


def assert_notification(entries: list[StreamEvent]) -> None:
    assert len(entries) == 1
    event = entries[0].event
    assert event.event_type == "connector.discovery.changed"
    assert event.subject == "connector:personal"
    assert event.metadata == {
        "connector_kind": "downstream_mcp",
        "connector_id": "personal",
    }
    assert set(event.model_dump()) == {
        "event_type",
        "subject",
        "metadata",
        "occurred_at",
    }
    assert all(
        value not in event.model_dump_json()
        for value in ("owner", "trusted", "private", "token", "schema")
    )


def _tool(name: str) -> DiscoveredTool:
    return DiscoveredToolWithoutOutputSchema(
        identity=ToolIdentity(connector_id="personal", downstream_name=name),
        title="Private metadata",
        description="Private administrator description",
        input_schema={"type": "object"},
    )
