from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.auth import AuthContext
from fastmcp.tools import ToolResult

from tests.umbod.core.downstream_mcp_connectors.personal_tools.runtime_support import ExecutionCase, execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalRuntimeContext
from umbod.core.invocation import ConnectorInvocation, ConnectorInvocationPolicy, PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.tools import ConnectorToolSearchCandidate
from umbod.mcp.connectors.tools.deployment_modes.codemode.sandbox import FastMcpMontyCodeModeAdapter, OpenApiCodeModeInvocation
from umbod.mcp.connectors.tools.infrastructure.authorization import ConnectorToolAuthorizationScope, UnrestrictedConnectorTools
from umbod.mcp.downstream_mcp_connectors import ConnectorAwareDownstreamMcpToolProvider, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.downstream_mcp_connectors.personal_runtime import personal_tool_permission_check
from umbod.mcp.downstream_mcp_connectors.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.downstream_mcp_connectors.tool_invocation import AuthorizedPersonalTool
from umbod.mcp.logging import McpToolInvocationCompleted
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder

from tests.umbod.mcp.downstream_mcp_connectors.test_personal_oauth_guards import RejectingDownstreamFactory

__all__ = ["runtime_case"]


class InvocationLog:
    def __init__(self) -> None:
        self.events: list[McpToolInvocationCompleted] = []

    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        self.events.append(event)


class ApprovalMutation:
    def __init__(self, mutation: Callable[[], Awaitable[None]]) -> None:
        self._mutation = mutation
        self.invocations: list[ConnectorInvocation] = []

    async def evaluate(self, invocation: ConnectorInvocation) -> None:
        self.invocations.append(invocation)
        await self._mutation()


def provider_for(execution: ExecutionCase, policy: ConnectorInvocationPolicy, log: InvocationLog) -> ConnectorAwareDownstreamMcpToolProvider:
    stores = execution.case.bundle
    return ConnectorAwareDownstreamMcpToolProvider(definitions=stores.definitions, credentials=stores.credentials, catalogs=stores.catalogs, publishing=stores.publishing, activations=stores.activations, client_factory=RejectingDownstreamFactory(), permission_policy=UnrestrictedDownstreamToolPermissionPolicy(), connector_scope="", capability_description_overrides=SystemConnectorCapabilityDescriptionOverrideStore(), tool_invocation_logger=log, metrics_recorder=InMemoryMcpMetricsRecorder(), invocation_policy=policy, personal_runtime=execution.runtime)


class ProviderGateway:
    def __init__(self, provider: ConnectorAwareDownstreamMcpToolProvider) -> None:
        self._provider = provider

    async def eligible_search_candidates(self, authorization_scope: ConnectorToolAuthorizationScope) -> list[ConnectorToolSearchCandidate]:
        return await self._provider.eligible_search_candidates()

    async def execute_tool(self, tool_name: str, arguments: Mapping[str, Any], authorization_scope: ConnectorToolAuthorizationScope) -> ToolResult:
        return await self._provider.execute_tool(tool_name, arguments)


class RejectingOpenApiExecutor:
    async def execute(self, invocation: OpenApiCodeModeInvocation) -> object:
        raise AssertionError("No OpenAPI fallback")


@pytest.mark.asyncio
@pytest.mark.parametrize("exposure", ("flat", "gateway", "codemode"))
async def test_personal_exposure_modes_share_approval_and_telemetry(runtime_case: RuntimeCase, exposure: str) -> None:
    execution = await execution_case(runtime_case)
    log = InvocationLog()
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), log)
    public = FastMCP("personal", providers=[provider])
    if exposure == "gateway":
        @public.tool(name="execute_personal")
        async def execute_personal() -> ToolResult:
            return await provider.execute_tool("Personal_read", {"value": "same"})
    async with Client(public) as client:
        if exposure == "codemode":
            result = await FastMcpMontyCodeModeAdapter(5).execute('Personal_read(value="same")', ProviderGateway(provider), UnrestrictedConnectorTools(), RejectingOpenApiExecutor())
            assert result.outcome == "success"
            assert result.final_value == {"owner": "owner"}
        else:
            result = await client.call_tool_mcp("execute_personal" if exposure == "gateway" else "Personal_read", {} if exposure == "gateway" else {"value": "same"})
            assert result.structured_content == {"owner": "owner"}
    assert len(execution.transport.calls) == 1
    assert len(log.events) == 1
    assert "owner-token" not in str(log.events)
    assert await provider.owns_tool("Personal_read")
    assert await provider.is_eligible("personal", "read")


@pytest.mark.asyncio
async def test_held_personal_tool_resolves_new_owner_after_approval(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)

    async def switch_owner() -> None:
        execution.contexts.contexts[:] = [PersonalRuntimeContext(principal=CanonicalPrincipal(namespace="trusted", subject="other"), group_ids=("team",))]

    policy = ApprovalMutation(switch_owner)
    provider = provider_for(execution, policy, InvocationLog())
    held = await provider.get_tool("Personal_read")
    assert isinstance(held, AuthorizedPersonalTool)
    result = await held.run({"value": "same"})
    assert result.is_error
    assert len(policy.invocations) == 1
    assert execution.transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ("disable", "disconnect", "publication", "activation", "capability_grant", "connector_grant", "policy"))
async def test_authority_withdrawn_during_approval_prevents_call(runtime_case: RuntimeCase, revocation: str) -> None:
    execution = await execution_case(runtime_case)

    async def revoke() -> None:
        if revocation == "disable":
            await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
        elif revocation == "disconnect":
            await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
        elif revocation == "publication":
            await runtime_case.bundle.publishing.unpublish_connector("personal")
        elif revocation == "activation":
            from umbod.core.activation import ActivationStatus, CapabilityRef
            await runtime_case.bundle.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key="read"), ActivationStatus.DISABLED)
        elif revocation == "policy":
            from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import replace_policy
            await replace_policy(runtime_case, ())
        else:
            from umbod.core.permissions.stores.schema import CAPABILITY_PERMISSION_TABLE, CONNECTOR_PERMISSION_TABLE
            from umbod.core.persistence import DeleteQuery, NoFilter, TransactionMode
            async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                await session.delete(CAPABILITY_PERMISSION_TABLE if revocation == "capability_grant" else CONNECTOR_PERMISSION_TABLE, DeleteQuery(NoFilter()))

    policy = ApprovalMutation(revoke)
    held = await provider_for(execution, policy, InvocationLog()).get_tool("Personal_read")
    result = await held.run({"value": "same"})
    assert result.is_error
    assert execution.transport.calls == []


@pytest.mark.asyncio
async def test_authoritative_component_type_ignores_cached_allow_and_deny(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    held = await provider.get_tool("Personal_read")
    clone = held.model_copy()
    assert isinstance(clone, AuthorizedPersonalTool)
    assert await personal_tool_permission_check(lambda context: False)(AuthContext(token=None, component=clone))
    await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    assert not await personal_tool_permission_check(lambda context: True)(AuthContext(token=None, component=clone))


@pytest.mark.asyncio
async def test_connector_scope_prevents_personal_cross_connector_dispatch(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    token = set_request_connector_scope("other")
    try:
        assert await provider.list_tools() == []
        assert await provider.eligible_search_candidates() == []
        assert not await provider.owns_tool("Personal_read")
        assert not await provider.is_eligible("personal", "read")
        with pytest.raises(Exception, match="not available"):
            await provider.execute_tool("Personal_read", {"value": "same"})
    finally:
        reset_request_connector_scope(token)
    token = set_request_connector_scope("personal")
    try:
        assert [tool.name for tool in await provider.list_tools()] == ["read"]
        assert await provider.owns_tool("read")
        assert (await provider.execute_tool("read", {"value": "same"})).structured_content == {"owner": "owner"}
    finally:
        reset_request_connector_scope(token)
