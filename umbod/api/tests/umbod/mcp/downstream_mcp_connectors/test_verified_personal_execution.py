from dataclasses import replace

import pytest
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from pydantic import SecretStr

from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool
from tests.umbod.mcp.test_personal_caller import _settings
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_tools.service import PersonalToolDiscoveryService
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider, McpPersonalToolRuntime

__all__ = ["runtime_case"]


@pytest.mark.asyncio
async def test_retained_tool_cannot_cross_owner_inventory_and_fresh_tool_uses_owner_schema(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    key = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="bob"), connector_id="personal")
    await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    query = runtime_case.query.model_copy(update={"key": key})
    grant = runtime_case.grant.model_copy(update={"key": key, "access_token": SecretStr("bob-only-token")})
    bob = RuntimeCase(runtime_case.database, runtime_case.bundle, runtime_case.store, query, grant)
    await install_authorization(bob, authorize_personal_grant(grant))
    bob_tool = approved_tool("read").model_copy(update={"input_schema": {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"], "additionalProperties": False}})
    execution.transport.inventories[key] = PersonalToolInventory(tools=(bob_tool,))
    await PersonalToolDiscoveryService(bob.store, bob.bundle.personal_tool_access, execution.transport, lambda: bob.query.now).discover(bob.query)
    execution.transport.results[(key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "bob"}})
    settings = _settings(namespace="trusted")
    settings = settings.model_copy(update={"mcp": settings.mcp.model_copy(update={"permission_group_claim": "groups"})})
    runtime = McpPersonalToolRuntime(McpPersonalCallerProvider(settings), runtime_case.bundle.definitions, runtime_case.bundle.personal_tool_access, execution.transport, lambda: runtime_case.query.now)
    provider = await provider_for(replace(execution, runtime=runtime), PermitAllConnectorInvocationPolicy(), InvocationLog())
    alice_token = AccessToken(token="alice-upstream", client_id="alice-client", scopes=[], claims={"sub": "owner", "groups": ["team"]})
    marker = auth_context_var.set(AuthenticatedUser(alice_token))
    try:
        held = await provider.get_tool("Personal_read")
        assert held is not None
        assert (await held.run({"value": "same"})).structured_content == {"owner": "owner"}
    finally:
        auth_context_var.reset(marker)
    bob_token = AccessToken(token="bob-upstream", client_id="bob-client", scopes=[], claims={"sub": "bob", "groups": ["team"]})
    marker = auth_context_var.set(AuthenticatedUser(bob_token))
    try:
        assert (await held.run({"value": "same"})).is_error
        bob_held = await provider.get_tool("Personal_read")
        assert bob_held.parameters["properties"]["value"]["type"] == "integer"
        candidates = await provider.eligible_search_candidates()
        assert candidates[0].input_schema["properties"]["value"]["type"] == "integer"
        assert (await bob_held.run({"value": 7})).structured_content == {"owner": "bob"}
    finally:
        auth_context_var.reset(marker)
    assert [call.target.access_token.get_secret_value() for call in execution.transport.calls] == ["owner-token", "bob-only-token"]
    assert (await held.run({"value": "same"})).is_error
    assert len(execution.transport.calls) == 2
