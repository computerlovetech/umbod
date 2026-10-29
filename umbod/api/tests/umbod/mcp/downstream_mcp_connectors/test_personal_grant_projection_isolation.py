import asyncio
from dataclasses import replace

import pytest
from fastmcp.exceptions import ToolError
from messaging.in_memory import (
    InMemoryEventCheckpointStoreFactory,
    InMemoryEventCheckpointStoreMessages,
)
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import (
    captured_personal_caller,
)
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import (
    RuntimeCase,
    install_authorization,
    runtime_case,
)
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import (
    approved_tool,
)
from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import (
    CurrentContext,
    ExecutionCase,
    execution_case,
)
from tests.umbod.mcp.downstream_mcp_connectors.signal_support import invocation_signals
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import (
    InvocationLog,
)
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_oauth_guards import (
    RejectingDownstreamFactory,
)
from umbod.core.capabilities.descriptions import (
    SystemConnectorCapabilityDescriptionOverrideStore,
)
from umbod.core.connectors.downstream_mcp.personal_connections import (
    CanonicalPrincipal,
    PersonalConnectionKey,
    SetPersonalConnectionEnabled,
)
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import (
    authorize_personal_grant,
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import (
    PersonalRuntimeUnavailable,
    PersonalRuntimeTarget,
    PersonalToolCall,
    PersonalToolInventory,
    PersonalToolResult,
)
from umbod.core.connectors.downstream_mcp.personal_tools.models import (
    PersonalToolDiscoveryQuery,
    PersonalToolRecord,
)
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery
from umbod.core.connectors.downstream_mcp.personal_tools.service import (
    PersonalToolDiscoveryService,
)
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.core.permissions import (
    InMemoryGroupConnectorToolPermissions,
    SaveGroupPermissionsRequest,
)
from umbod.core.permissions.factories import create_group_permission_store
from umbod.mcp.connectors.downstream_mcp import (
    ConnectorAwareDownstreamMcpToolProvider,
    UnrestrictedDownstreamToolPermissionPolicy,
)
from umbod.mcp.connectors.downstream_mcp.personal_discovery import (
    PersonalDiscoveryOperations,
)
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalToolRuntime
from umbod.mcp.connectors.downstream_mcp.runtime import (
    DownstreamDiscoveryStores,
    create_downstream_discovery_runtime,
)
from umbod.mcp.connectors.downstream_mcp.tool_invocation import AuthorizedPersonalTool
from umbod.mcp.live_permission_updates import (
    DatabaseGroupPermissionReader,
    GroupPermissionStateReloader,
)
from umbod.mcp.messaging import RuntimeProjectionHealth, RuntimeProjectionSynchronizer
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import SignalToolExecutionPipelineFactory

__all__ = ["runtime_case"]


@pytest.fixture(params=[
    CanonicalPrincipal(namespace="trusted", subject="bob"),
    CanonicalPrincipal(namespace="other", subject="owner"),
], ids=["distinct-subject", "distinct-namespace"])
def bob_principal(request: pytest.FixtureRequest) -> CanonicalPrincipal:
    return request.param


class GatedPersonalTransport:
    def __init__(self, delegate: InMemoryPersonalMcpTransport) -> None:
        self._delegate = delegate
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.pending: list[PersonalToolCall] = []

    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory:
        return await self._delegate.list_tools(target)

    async def call_tool(self, command: PersonalToolCall) -> PersonalToolResult:
        self.pending.append(command)
        self.entered.set()
        await self.release.wait()
        return await self._delegate.call_tool(command)


async def install_bob(execution: ExecutionCase, principal: CanonicalPrincipal) -> ExecutionCase:
    case = execution.case
    key = PersonalConnectionKey(
        principal=principal,
        connector_id="personal",
    )
    await case.bundle.personal_connections.set_enabled(
        SetPersonalConnectionEnabled(key=key, enabled=True)
    )
    query = case.query.model_copy(update={"key": key})
    grant = case.grant.model_copy(
        update={"key": key, "access_token": SecretStr("bob-only-token")}
    )
    bob = RuntimeCase(case.database, case.bundle, case.store, query, grant)
    await install_authorization(bob, authorize_personal_grant(grant))
    execution.transport.inventories[key] = PersonalToolInventory(
        tools=(approved_tool("read"),)
    )
    execution.transport.results[(key, "read")] = PersonalToolResult(
        result={"content": [], "structuredContent": {"owner": "bob"}}
    )
    await PersonalToolDiscoveryService(
        bob.store, bob.bundle.personal_tool_access, execution.transport, lambda: query.now
    ).discover(query)
    contexts = CurrentContext(captured_personal_caller(key.principal, query.group_ids))
    runtime = McpPersonalToolRuntime(
        contexts, bob.bundle.personal_tool_access, execution.transport, lambda: query.now
    )
    return replace(execution, case=bob, contexts=contexts, runtime=runtime)


async def inventory_records(execution: ExecutionCase) -> tuple[PersonalToolRecord, ...]:
    case = execution.case
    definition = await case.bundle.definitions.get(ConnectorIdQuery(connector_id="personal"))
    return await case.bundle.personal_tool_discovery.read(
        PersonalToolDiscoveryQuery(
            principal=case.query.key.principal,
            definitions=(definition.definition,),
            now=case.query.now,
        )
    )


async def projected_provider(
    execution: ExecutionCase,
    permissions: InMemoryGroupConnectorToolPermissions,
) -> ConnectorAwareDownstreamMcpToolProvider:
    stores = execution.case.bundle
    discovery = create_downstream_discovery_runtime(
        DownstreamDiscoveryStores(
            definitions=stores.definitions,
            credentials=stores.credentials,
            catalogs=stores.catalogs,
            publishing=stores.publishing,
            activations=stores.activations,
            descriptions=SystemConnectorCapabilityDescriptionOverrideStore(),
        )
    )
    await discovery.reconcile()
    policy = UnrestrictedDownstreamToolPermissionPolicy()
    personal_discovery = PersonalDiscoveryOperations(
        discovery,
        execution.contexts,
        stores.personal_tool_discovery,
        permissions,
        lambda: execution.case.query.now,
        policy,
    )
    signals = invocation_signals(InMemoryMcpMetricsRecorder(), InvocationLog())
    return ConnectorAwareDownstreamMcpToolProvider(
        discovery_runtime=discovery,
        personal_discovery=personal_discovery,
        definitions=stores.definitions,
        credentials=stores.credentials,
        catalogs=stores.catalogs,
        publishing=stores.publishing,
        activations=stores.activations,
        client_factory=RejectingDownstreamFactory(),
        permission_policy=policy,
        connector_scope="",
        signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(
            signals, PermitAllConnectorInvocationPolicy()
        ),
        personal_runtime=execution.runtime,
    )


def projection_consumer(
    case: RuntimeCase, permissions: InMemoryGroupConnectorToolPermissions
) -> RuntimeProjectionSynchronizer:
    reloader = GroupPermissionStateReloader(
        permission_reader=DatabaseGroupPermissionReader(case.database),
        runtime_permissions=permissions,
    )

    async def reconcile() -> None:
        assert await reloader.reload_group_permissions()

    return RuntimeProjectionSynchronizer(
        DatabaseEventStream(case.database),
        InMemoryEventCheckpointStoreFactory(
            InMemoryEventCheckpointStoreMessages()
        ).create(),
        reconcile,
        RuntimeProjectionHealth(),
        interval_seconds=1.0,
        batch_limit=1000,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("disable_alice", (False, True))
async def test_shared_grant_projection_lag_hides_bob_independently_of_alice_disable(
    runtime_case: RuntimeCase, bob_principal: CanonicalPrincipal, disable_alice: bool
) -> None:
    alice = await execution_case(runtime_case)
    bob = await install_bob(alice, bob_principal)
    store = await create_group_permission_store(runtime_case.database)
    await store.register_group("team")
    alice_permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    bob_permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    alice_projection = projection_consumer(runtime_case, alice_permissions)
    bob_projection = projection_consumer(runtime_case, bob_permissions)
    await alice_projection.bootstrap()
    await bob_projection.bootstrap()
    alice_provider = await projected_provider(alice, alice_permissions)
    bob_provider = await projected_provider(bob, bob_permissions)
    alice_tool = await alice_provider.get_tool("Personal_read")
    bob_tool = await bob_provider.get_tool("Personal_read")
    assert isinstance(alice_tool, AuthorizedPersonalTool)
    assert isinstance(bob_tool, AuthorizedPersonalTool)
    assert (await alice_tool.run({"value": "same"})).structured_content == {"owner": "owner"}
    assert (await bob_tool.run({"value": "same"})).structured_content == {"owner": "bob"}
    assert [call.target.key for call in alice.transport.calls] == [runtime_case.query.key, bob.case.query.key]
    assert [call.target.access_token.get_secret_value() for call in alice.transport.calls] == ["owner-token", "bob-only-token"]
    bob_connection = await bob.case.bundle.personal_connections.get(bob.case.query.key)
    bob_records = await inventory_records(bob)
    assert len(bob_records) == 1
    bob_inventory = await bob.case.bundle.personal_tool_access.read_inventory_revision(bob.case.query)
    list_requests = len(alice.transport.list_requests)

    await store.save_group_permissions(
        SaveGroupPermissionsRequest(group_id="team", connector_ids=(), capabilities=())
    )
    assert isinstance(await alice_provider.get_tool("Personal_read"), AuthorizedPersonalTool)
    assert isinstance(await bob_provider.get_tool("Personal_read"), AuthorizedPersonalTool)
    for execution, tool in ((alice, alice_tool), (bob, bob_tool)):
        with pytest.raises(PersonalRuntimeUnavailable):
            await execution.case.store.resolve(execution.case.query)
        assert (await tool.run({"value": "same"})).is_error
    assert len(alice.transport.calls) == 2
    assert len(alice.transport.list_requests) == list_requests
    assert await alice_projection.poll_once()
    assert await bob_projection.poll_once()
    assert await alice_provider.get_tool("Personal_read") is None
    assert await bob_provider.get_tool("Personal_read") is None

    await store.save_group_permissions(
        SaveGroupPermissionsRequest(group_id="team", connector_ids=("personal",), capabilities=())
    )
    if disable_alice:
        await runtime_case.bundle.personal_connections.set_enabled(
            SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False)
        )
    assert await alice_projection.poll_once()
    assert await bob.case.bundle.personal_connections.get(bob.case.query.key) == bob_connection
    assert await bob.case.bundle.personal_tool_access.read_inventory_revision(bob.case.query) == bob_inventory
    assert (await bob.case.store.resolve(bob.case.query)).access_token.get_secret_value() == "bob-only-token"
    assert await bob_provider.get_tool("Personal_read") is None
    with pytest.raises(ToolError, match="not available"):
        await bob_provider.execute_tool("Personal_read", {"value": "same"})
    assert len(alice.transport.calls) == 2
    assert len(alice.transport.list_requests) == list_requests

    assert await bob_projection.poll_once()
    recovered = await bob_provider.get_tool("Personal_read")
    assert isinstance(recovered, AuthorizedPersonalTool)
    assert await bob.case.bundle.personal_connections.get(bob.case.query.key) == bob_connection
    assert await bob.case.bundle.personal_tool_access.read_inventory_revision(bob.case.query) == bob_inventory
    assert await inventory_records(bob) == bob_records
    assert len(alice.transport.list_requests) == list_requests
    assert (await recovered.run({"value": "same"})).structured_content == {"owner": "bob"}
    assert alice.transport.calls[-1].target.key == bob.case.query.key
    assert alice.transport.calls[-1].target.access_token.get_secret_value() == "bob-only-token"
    if disable_alice:
        assert await alice_provider.get_tool("Personal_read") is None
        assert (await alice_tool.run({"value": "same"})).is_error
    else:
        assert isinstance(await alice_provider.get_tool("Personal_read"), AuthorizedPersonalTool)
    assert len(alice.transport.calls) == 3
    assert not await bob_projection.poll_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ("disable", "disconnect"))
async def test_alice_revocation_concurrent_with_bob_call_preserves_bob_state_and_token(
    runtime_case: RuntimeCase, bob_principal: CanonicalPrincipal, transition: str
) -> None:
    alice = await execution_case(runtime_case)
    bob = await install_bob(alice, bob_principal)
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.grant_connector("team", "personal")
    gated = GatedPersonalTransport(bob.transport)
    bob = replace(bob, runtime=McpPersonalToolRuntime(
        bob.contexts, bob.case.bundle.personal_tool_access, gated, lambda: bob.case.query.now,
    ))
    alice_provider = await projected_provider(alice, permissions)
    bob_provider = await projected_provider(bob, permissions)
    alice_tool = await alice_provider.get_tool("Personal_read")
    assert isinstance(alice_tool, AuthorizedPersonalTool)
    connection = await bob.case.bundle.personal_connections.get(bob.case.query.key)
    records = await inventory_records(bob)
    assert len(records) == 1
    inventory = await bob.case.bundle.personal_tool_access.read_inventory_revision(bob.case.query)

    async def revoke_alice() -> None:
        if transition == "disable":
            await runtime_case.bundle.personal_connections.set_enabled(
                SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False)
            )
        else:
            await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)

    invocation = asyncio.create_task(bob_provider.execute_tool("Personal_read", {"value": "same"}))
    try:
        await asyncio.wait_for(gated.entered.wait(), timeout=5)
        assert not invocation.done()
        assert gated.pending[0].target.key == bob.case.query.key
        assert gated.pending[0].target.access_token.get_secret_value() == "bob-only-token"
        await asyncio.wait_for(revoke_alice(), timeout=5)
        assert not invocation.done()
    finally:
        gated.release.set()
        result = await asyncio.wait_for(invocation, timeout=5)
    assert result.structured_content == {"owner": "bob"}
    assert await bob.case.bundle.personal_connections.get(bob.case.query.key) == connection
    assert await bob.case.bundle.personal_tool_access.read_inventory_revision(bob.case.query) == inventory
    assert await inventory_records(bob) == records
    assert await alice_provider.get_tool("Personal_read") is None
    assert (await alice_tool.run({"value": "same"})).is_error
    assert len(alice.transport.calls) == 1
    call = alice.transport.calls[0]
    assert call.target.key == bob.case.query.key
    assert call.target.access_token.get_secret_value() == "bob-only-token"
    assert (await bob_provider.execute_tool("Personal_read", {"value": "same"})).structured_content == {"owner": "bob"}
    assert len(alice.transport.calls) == 2
    assert all(call.target.key == bob.case.query.key for call in alice.transport.calls)
    assert all(call.target.access_token.get_secret_value() == "bob-only-token" for call in alice.transport.calls)
