from datetime import timedelta

import pytest
from pydantic import SecretStr

from tests.umbod.core.connectors.downstream_mcp.personal_caller_support import captured_personal_caller
from tests.umbod.core.connectors.downstream_mcp.personal_discovery_support import read_available
from tests.umbod.core.connectors.downstream_mcp.test_personal_refresh import command, refresh_store, reservation
from tests.umbod.core.connectors.downstream_mcp.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from umbod.core.connectors.downstream_mcp.personal.connections import CanonicalPrincipal, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal.oauth.grants.models import authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal.oauth.refresh.models import FailPersonalRefresh
from umbod.core.connectors.downstream_mcp.personal.connections.health_models import RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal.oauth.refresh.ports import PersonalRefreshStore
from umbod.core.connectors.downstream_mcp.personal.tools.runtime_models import PersonalAuthorizationRequired, PersonalInventoryRefreshRequired, PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal.tools import PersonalToolDiscoveryQuery, PersonalToolDiscoveryService, PersonalToolRuntimeService, SavePersonalToolObservation
from umbod.core.connectors.downstream_mcp.personal.oauth.configuration import PersonalOAuthConfigurationQuery, ReplacePersonalOAuthConfiguration, PersonalOAuthSettings
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery
from umbod.core.permissions.stores.schema import CONNECTOR_PERMISSION_TABLE
from umbod.core.persistence import DeleteQuery, NoFilter, TransactionMode

from .runtime_support import execution_case, runtime_for_caller

__all__ = ["runtime_case", "refresh_store"]


async def reject_authorization(case: RuntimeCase) -> None:
    connection = await case.bundle.personal_connections.get(case.query.key)
    await case.bundle.personal_tool_access.reject_authorization(RejectPersonalAuthorization(key=case.query.key, expected_connection_revision=connection.revision))


@pytest.mark.asyncio
@pytest.mark.parametrize("block,reason", [("expired", "expired"), ("rejected", "rejected"), ("preparing", "refresh_in_progress"), ("exchanging", "refresh_in_progress"), ("exchange_expired", "refresh_blocked"), ("refresh_uncertain", "refresh_blocked"), ("refresh_denied", "refresh_blocked")])
async def test_known_authorization_block_retains_descriptors_without_downstream_call(runtime_case: RuntimeCase, refresh_store: PersonalRefreshStore, block: str, reason: str) -> None:
    execution = await execution_case(runtime_case)
    previous = await read_available(runtime_case.bundle, runtime_case.query)
    definitions = (await runtime_case.bundle.definitions.list()).definitions
    assert len(await runtime_case.bundle.personal_tool_discovery.read_available(PersonalToolDiscoveryQuery(principal=runtime_case.query.key.principal, definitions=definitions, now=runtime_case.query.now))) == 1
    now = runtime_case.query.now
    if block == "expired":
        now += timedelta(hours=2)
    elif block == "rejected":
        await reject_authorization(runtime_case)
    else:
        await refresh_store.reserve(reservation(runtime_case))
        if block != "preparing":
            await refresh_store.exchange(command(runtime_case))
        if block == "exchange_expired":
            now += timedelta(seconds=31)
        elif block in ("refresh_uncertain", "refresh_denied"):
            await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason=block))
    query = runtime_case.query.model_copy(update={"now": now})
    assert await read_available(runtime_case.bundle, query) == previous
    assert await runtime_case.bundle.personal_tool_discovery.read_available(PersonalToolDiscoveryQuery(principal=query.key.principal, definitions=definitions, now=now)) == ()
    runtime = PersonalToolRuntimeService(execution.caller, runtime_case.bundle.personal_tool_access, execution.transport, lambda: now)
    for _ in range(2):
        with pytest.raises(PersonalAuthorizationRequired) as caught:
            await runtime.execute(execution.command)
        assert caught.value.reason == reason
        assert "owner-token" not in str(caught.value)
    assert execution.transport.calls == []
    assert execution.transport.list_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("staleness", ["expired_observation", "reconnected"])
async def test_expected_inventory_requires_loading_tools_after_staleness_without_false_sign_in(runtime_case: RuntimeCase, staleness: str) -> None:
    execution = await execution_case(runtime_case)
    now = runtime_case.query.now
    invocation = execution.command
    if staleness == "expired_observation":
        target = await runtime_case.store.resolve(runtime_case.query)
        records = await read_available(runtime_case.bundle, runtime_case.query)
        await runtime_case.bundle.personal_tool_access.save_observation(SavePersonalToolObservation(query=runtime_case.query, target=target, expected_inventory_revision=await runtime_case.bundle.personal_tool_access.read_inventory_revision(runtime_case.query), tools=tuple(record.tool for record in records), expires_at=now + timedelta(seconds=10)))
        current = (await read_available(runtime_case.bundle, runtime_case.query))[0]
        invocation = invocation.model_copy(update={"inventory_revision": current.inventory_revision})
        now += timedelta(seconds=11)
    previous = await read_available(runtime_case.bundle, runtime_case.query)
    if staleness == "reconnected":
        now += timedelta(hours=2)
        for token in ("replacement-one", "replacement-two"):
            grant = runtime_case.grant.model_copy(update={"access_token": SecretStr(token), "issued_at": now, "lifetime": runtime_case.grant.lifetime.model_copy(update={"expires_at": now + timedelta(hours=1)})})
            await install_authorization(runtime_case, authorize_personal_grant(grant))
            assert await read_available(runtime_case.bundle, runtime_case.query.model_copy(update={"now": now})) == previous
    query = runtime_case.query.model_copy(update={"now": now})
    assert await read_available(runtime_case.bundle, query) == previous
    runtime = PersonalToolRuntimeService(execution.caller, runtime_case.bundle.personal_tool_access, execution.transport, lambda: now)
    definitions = (await runtime_case.bundle.definitions.list()).definitions
    discovery_query = PersonalToolDiscoveryQuery(principal=query.key.principal, definitions=definitions, now=now)
    assert await runtime_case.bundle.personal_tool_discovery.read_available(discovery_query) == ()
    with pytest.raises(PersonalInventoryRefreshRequired):
        await runtime.execute(invocation)
    assert execution.transport.calls == []
    assert execution.transport.list_requests == []
    discovery = PersonalToolDiscoveryService(runtime_case.store, runtime_case.bundle.personal_tool_access, execution.transport, lambda: now)
    await discovery.discover(query)
    assert len(await runtime_case.bundle.personal_tool_discovery.read_available(discovery_query)) == 1
    assert execution.transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ["revision", "fingerprint", "invented", "foreign"])
async def test_recovery_is_not_disclosed_for_unknown_or_stale_contract(runtime_case: RuntimeCase, invalidity: str) -> None:
    execution = await execution_case(runtime_case)
    await reject_authorization(runtime_case)
    invocation = execution.command
    runtime = execution.runtime
    if invalidity == "revision":
        invocation = invocation.model_copy(update={"inventory_revision": "stale"})
    elif invalidity == "fingerprint":
        invocation = invocation.model_copy(update={"fingerprint": "0" * 64})
    elif invalidity == "invented":
        invocation = invocation.model_copy(update={"identity": invocation.identity.model_copy(update={"capability_key": "invented"})})
    else:
        principal = CanonicalPrincipal(namespace="trusted", subject="unrelated")
        runtime = runtime_for_caller(execution, captured_personal_caller(principal, ("team",)))
        query = runtime_case.query.model_copy(update={"key": runtime_case.query.key.model_copy(update={"principal": principal})})
        assert await read_available(runtime_case.bundle, query) == ()
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await runtime.execute(invocation)
    assert not isinstance(caught.value, PersonalAuthorizationRequired)
    assert str(caught.value) == "Personal tool unavailable"
    assert execution.transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["disable", "disconnect", "unpublish", "permission", "configuration", "delete"])
async def test_revocation_overrides_recovery_and_owner_mutations_hide_rejected_inventory(runtime_case: RuntimeCase, mutation: str) -> None:
    execution = await execution_case(runtime_case)
    await reject_authorization(runtime_case)
    if mutation == "disable":
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
    elif mutation == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    elif mutation == "unpublish":
        await runtime_case.bundle.publishing.unpublish_connector("personal")
    elif mutation == "permission":
        async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.delete(CONNECTOR_PERMISSION_TABLE, DeleteQuery(NoFilter()))
    elif mutation == "delete":
        await runtime_case.bundle.definitions.delete(ConnectorIdQuery(connector_id="personal"))
    else:
        configuration = await runtime_case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
        await runtime_case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision=configuration.policy.revision, settings=PersonalOAuthSettings(requested_scopes=("different",), client=configuration.policy.client)))
    if mutation not in ("unpublish", "permission"):
        assert await read_available(runtime_case.bundle, runtime_case.query) == ()
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await execution.runtime.execute(execution.command)
    assert not isinstance(caught.value, PersonalAuthorizationRequired)
    assert execution.transport.calls == []
