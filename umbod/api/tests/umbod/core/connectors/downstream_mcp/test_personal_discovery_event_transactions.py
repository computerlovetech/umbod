from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from unittest.mock import Mock

import pytest
from messaging.models import StreamEvent

from tests.umbod.core.connectors.downstream_mcp.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.connectors.downstream_mcp.test_personal_policy_event_transactions import _tool
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable, RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.models import Authorized, ReplacePersonalAuthorization, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationQuery, PersonalOAuthSettings, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.personal_tools import MissingInventoryRevision, ReplacePersonalToolPolicy, SavePersonalToolObservation
from umbod.core.connectors.downstream_mcp.stores.personal_authorization_health_schema import PERSONAL_AUTHORIZATION_REJECTION_TABLE
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configuration_schema import PERSONAL_OAUTH_CONFIGURATION_TABLE
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_schema import PERSONAL_OAUTH_ATTEMPT_TABLE
from umbod.core.connectors.downstream_mcp.stores.personal_refresh_schema import PERSONAL_REFRESH_TABLE
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_schema import PERSONAL_DISCOVERY_TABLE
from umbod.core.connectors.downstream_mcp.stores.personal_tools_schema import PERSONAL_TOOL_OBSERVATION_TABLE, PERSONAL_TOOL_POLICY_TABLE
from umbod.core.connectors.downstream_mcp.stores.schema import PERSONAL_CONNECTION_TABLE
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.core.messaging.stores.schema import EVENT_TABLE, MessagingEventKey, MessagingEventRecord
from umbod.core.persistence import AllFields, Database, DatabaseSession, GeneratedIntegerKeyInsertCommand, NoFilter, Query, Table, TransactionMode, Unordered

__all__ = ["runtime_case"]

Mutation = Callable[[], Awaitable[object]]
OPERATIONS = ("enable", "disconnect", "authorization", "rejection", "observation", "configuration", "delete_connection", "delete_policy", "delete_configuration")


async def events(database: Database) -> list[StreamEvent]:
    return await DatabaseEventStream(database).list_after(0, 1000)


async def snapshot(database: Database) -> tuple[object, ...]:
    tables = (PERSONAL_DISCOVERY_TABLE, PERSONAL_CONNECTION_TABLE, PERSONAL_AUTHORIZATION_REJECTION_TABLE, PERSONAL_REFRESH_TABLE, PERSONAL_OAUTH_CONFIGURATION_TABLE, PERSONAL_OAUTH_ATTEMPT_TABLE, PERSONAL_TOOL_OBSERVATION_TABLE, PERSONAL_TOOL_POLICY_TABLE)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        return tuple([tuple(await session.find_many(table, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))) for table in tables])


def reject_events(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    original_session = database.session

    @asynccontextmanager
    async def rejecting_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with original_session(mode=mode) as session:
            async def insert_event(
                table: Table[MessagingEventRecord, MessagingEventKey],
                command: GeneratedIntegerKeyInsertCommand[MessagingEventRecord],
            ) -> int:
                if table == EVENT_TABLE and command.row.event_type == "connector.discovery.changed":
                    raise RuntimeError("event append failed")
                return await session.insert_generated_integer_key(table, command)

            rejecting = Mock(spec=DatabaseSession, wraps=session)
            rejecting.insert_generated_integer_key.side_effect = insert_event
            yield rejecting

    monkeypatch.setattr(database, "session", rejecting_session)


def assert_notification(entries: list[StreamEvent]) -> None:
    assert len(entries) == 1
    event = entries[0].event
    assert event.event_type == "connector.discovery.changed"
    assert event.subject == "connector:personal"
    assert event.metadata == {"connector_kind": "downstream_mcp", "connector_id": "personal"}
    assert set(event.model_dump()) == {"event_type", "subject", "metadata", "occurred_at"}
    assert all(value not in event.model_dump_json() for value in ("owner", "trusted", "private", "token", "schema"))


async def mutation(case: RuntimeCase, operation: str) -> Mutation:
    stores = case.bundle
    key = case.query.key
    current = await stores.personal_connections.get(key)
    configuration = await stores.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
    if operation == "enable":
        return lambda: stores.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=False))
    if operation == "disconnect":
        return lambda: stores.personal_connections.disconnect(key)
    if operation == "authorization":
        return lambda: stores.personal_connections.replace_authorization(ReplacePersonalAuthorization(key=key, expected_revision=current.revision, authorization=Authorized(authorization="private-replacement")))
    if operation == "rejection":
        return lambda: stores.personal_tool_access.reject_authorization(RejectPersonalAuthorization(key=key, expected_connection_revision=current.revision))
    if operation == "observation":
        target = await case.store.resolve(case.query)
        return lambda: stores.personal_tool_access.save_observation(SavePersonalToolObservation(query=case.query, target=target, expected_inventory_revision=MissingInventoryRevision(kind="missing"), tools=(_tool("private-tool"),), expires_at=target.expires_at))
    if operation == "configuration":
        return lambda: stores.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision=configuration.policy.revision, settings=PersonalOAuthSettings(requested_scopes=("changed",), client=configuration.policy.client)))
    if operation == "delete_connection":
        return lambda: stores.personal_connections.delete_connector("personal")
    if operation == "delete_policy":
        await stores.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision="unconfigured", tools=(_tool("private-tool"),), native_identities=()))
        return lambda: stores.personal_tool_policies.delete_connector("personal")
    if operation == "delete_configuration":
        return lambda: stores.personal_oauth_configurations.delete_connector("personal")
    raise AssertionError(operation)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_personal_mutations_publish_only_sanitized_connector_notification(runtime_case: RuntimeCase, operation: str) -> None:
    run = await mutation(runtime_case, operation)
    before = await events(runtime_case.database)
    await run()
    assert_notification((await events(runtime_case.database))[len(before):])


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_event_failure_restores_personal_mutation(runtime_case: RuntimeCase, monkeypatch: pytest.MonkeyPatch, operation: str) -> None:
    run = await mutation(runtime_case, operation)
    before = await snapshot(runtime_case.database)
    previous_events = await events(runtime_case.database)
    reject_events(runtime_case.database, monkeypatch)
    error = PersonalAuthorizationHealthUnavailable if operation == "rejection" else RuntimeError
    with pytest.raises(error):
        await run()
    assert await snapshot(runtime_case.database) == before
    assert await events(runtime_case.database) == previous_events


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("enable", "rejection", "delete_connection", "delete_policy", "delete_configuration"))
async def test_repeated_personal_mutation_is_noop(runtime_case: RuntimeCase, operation: str) -> None:
    run = await mutation(runtime_case, operation)
    await run()
    before = await events(runtime_case.database)
    previous_state = await snapshot(runtime_case.database)
    await run()
    assert await events(runtime_case.database) == before
    assert await snapshot(runtime_case.database) == previous_state


@pytest.mark.asyncio
async def test_unchanged_configuration_and_stale_rejection_publish_nothing(runtime_case: RuntimeCase) -> None:
    configuration = await runtime_case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
    before = await events(runtime_case.database)
    await runtime_case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision=configuration.policy.revision, settings=PersonalOAuthSettings(requested_scopes=configuration.policy.requested_scopes, client=configuration.policy.client)))
    await runtime_case.bundle.personal_tool_access.reject_authorization(RejectPersonalAuthorization(key=runtime_case.query.key, expected_connection_revision="stale"))
    assert await events(runtime_case.database) == before


@pytest.mark.asyncio
async def test_aggregate_delete_keeps_its_single_notification(runtime_case: RuntimeCase) -> None:
    before = await events(runtime_case.database)
    await runtime_case.bundle.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    assert_notification((await events(runtime_case.database))[len(before):])


@pytest.mark.asyncio
async def test_missing_connection_disconnect_is_noop(runtime_case: RuntimeCase) -> None:
    await runtime_case.bundle.personal_connections.delete_connector("personal")
    before = await events(runtime_case.database)
    await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    assert await events(runtime_case.database) == before


@pytest.mark.asyncio
async def test_stale_observation_publishes_nothing(runtime_case: RuntimeCase) -> None:
    run = await mutation(runtime_case, "observation")
    await run()
    before = await events(runtime_case.database)
    with pytest.raises(PersonalRuntimeUnavailable):
        await run()
    assert await events(runtime_case.database) == before
