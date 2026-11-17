from collections.abc import Awaitable, Callable

import pytest

from tests.support.personal_runtime_cases import RuntimeCase
from tests.support.personal_discovery_events import (
    _tool,
    assert_notification as assert_notification,
    events as events,
    reject_events as reject_events,
    rollback_snapshot,
    rollback_snapshot as snapshot,
)
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthQuery, PersonalAuthorizationHealthUnavailable, RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.models import Authorized, ReplacePersonalAuthorization, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationQuery, PersonalOAuthSettings, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.personal_tools import MissingInventoryRevision, ReplacePersonalToolPolicy, SavePersonalToolObservation
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery

__all__ = ["snapshot"]

Mutation = Callable[[], Awaitable[object]]
OPERATIONS = ("enable", "disconnect", "authorization", "rejection", "observation", "configuration", "delete_connection", "delete_policy", "delete_configuration")


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


async def personal_mutation_state(case: RuntimeCase, operation: str) -> tuple[object, ...]:
    stores = case.bundle
    key = case.query.key
    if operation in {"enable", "delete_connection"}:
        return (await stores.personal_connections.get(key),)
    if operation == "rejection":
        return (
            await stores.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=key, now=case.query.now)),
            await stores.personal_connections.get(key),
        )
    if operation == "delete_policy":
        return (await stores.personal_tool_policies.get(ConnectorIdQuery(connector_id=key.connector_id)),)
    if operation == "delete_configuration":
        return (
            await stores.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id=key.connector_id)),
            await stores.personal_connections.get(key),
            await stores.publishing.is_published(key.connector_id),
        )
    raise AssertionError(operation)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_personal_mutations_publish_only_sanitized_connector_notification(discovery_runtime_case: RuntimeCase, operation: str) -> None:
    run = await mutation(discovery_runtime_case, operation)
    before = await events(discovery_runtime_case.database)
    await run()
    emitted = (await events(discovery_runtime_case.database))[len(before):]
    if operation in {"configuration", "delete_configuration"}:
        assert [entry.event.event_type for entry in emitted] == ["connector.publication.changed", "connector.discovery.changed"]
        assert not await discovery_runtime_case.bundle.publishing.is_published("personal")
        emitted = emitted[1:]
    assert_notification(emitted)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_event_failure_restores_personal_mutation(discovery_runtime_case: RuntimeCase, monkeypatch: pytest.MonkeyPatch, operation: str) -> None:
    run = await mutation(discovery_runtime_case, operation)
    before = await rollback_snapshot(discovery_runtime_case.database)
    previous_events = await events(discovery_runtime_case.database)
    reject_events(discovery_runtime_case.database, monkeypatch)
    error = PersonalAuthorizationHealthUnavailable if operation == "rejection" else RuntimeError
    with pytest.raises(error):
        await run()
    assert await rollback_snapshot(discovery_runtime_case.database) == before
    assert await events(discovery_runtime_case.database) == previous_events


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("enable", "rejection", "delete_connection", "delete_policy", "delete_configuration"))
async def test_repeated_personal_mutation_is_noop(discovery_runtime_case: RuntimeCase, operation: str) -> None:
    run = await mutation(discovery_runtime_case, operation)
    await run()
    before = await events(discovery_runtime_case.database)
    previous_state = await personal_mutation_state(discovery_runtime_case, operation)
    await run()
    assert await events(discovery_runtime_case.database) == before
    assert await personal_mutation_state(discovery_runtime_case, operation) == previous_state


@pytest.mark.asyncio
async def test_unchanged_configuration_and_stale_rejection_publish_nothing(discovery_runtime_case: RuntimeCase) -> None:
    configuration = await discovery_runtime_case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
    before = await events(discovery_runtime_case.database)
    await discovery_runtime_case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision=configuration.policy.revision, settings=PersonalOAuthSettings(requested_scopes=configuration.policy.requested_scopes, client=configuration.policy.client)))
    await discovery_runtime_case.bundle.personal_tool_access.reject_authorization(RejectPersonalAuthorization(key=discovery_runtime_case.query.key, expected_connection_revision="stale"))
    assert await events(discovery_runtime_case.database) == before


@pytest.mark.asyncio
async def test_aggregate_delete_keeps_its_single_notification(discovery_runtime_case: RuntimeCase) -> None:
    before = await events(discovery_runtime_case.database)
    await discovery_runtime_case.bundle.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    assert_notification((await events(discovery_runtime_case.database))[len(before):])


@pytest.mark.asyncio
async def test_missing_connection_disconnect_is_noop(discovery_runtime_case: RuntimeCase) -> None:
    await discovery_runtime_case.bundle.personal_connections.delete_connector("personal")
    before = await events(discovery_runtime_case.database)
    await discovery_runtime_case.bundle.personal_connections.disconnect(discovery_runtime_case.query.key)
    assert await events(discovery_runtime_case.database) == before


@pytest.mark.asyncio
async def test_stale_observation_publishes_nothing(discovery_runtime_case: RuntimeCase) -> None:
    run = await mutation(discovery_runtime_case, "observation")
    await run()
    before = await events(discovery_runtime_case.database)
    with pytest.raises(PersonalRuntimeUnavailable):
        await run()
    assert await events(discovery_runtime_case.database) == before
