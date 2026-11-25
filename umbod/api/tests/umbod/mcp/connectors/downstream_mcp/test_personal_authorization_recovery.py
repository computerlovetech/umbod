from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.middleware import AuthMiddleware
from pydantic import SecretStr

from tests.umbod.core.connectors.downstream_mcp.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from umbod.core.connectors.downstream_mcp.personal.oauth.grants.models import authorize_personal_grant
from tests.umbod.mcp.connectors.downstream_mcp.personal_runtime_support import execution_case
from tests.umbod.mcp.connectors.downstream_mcp.test_personal_execution_pipeline import InvocationLog, ProviderGateway, RejectingOpenApiExecutor, provider_for
from umbod.mcp.connectors.native.tools.deployment_modes.codemode.sandbox import FastMcpMontyCodeModeAdapter, FailedNestedConnectorCall
from umbod.mcp.connectors.native.tools.infrastructure.authorization import UnrestrictedConnectorTools
from umbod.core.connectors.downstream_mcp.personal.connections.health_models import RejectPersonalAuthorization
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalToolRuntime, PersonalDiscoveryMiddleware, PersonalToolReservationMiddleware, personal_tool_permission_check
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.connectors.downstream_mcp.personal_recovery import validate_recovery_origin

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_scope", ("", "personal"))
@pytest.mark.parametrize("authorization_state", ("expired", "rejected", "inventory_stale"))
async def test_expected_tool_returns_wire_recovery_error_without_downstream_call(runtime_case: RuntimeCase, connector_scope: str, authorization_state: str) -> None:
    execution = await execution_case(runtime_case)
    original = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    before = (await original.list_tools())[0]
    if authorization_state == "expired":
        current = replace(runtime_case, query=runtime_case.query.model_copy(update={"now": runtime_case.query.now + timedelta(days=1)}))
    elif authorization_state == "inventory_stale":
        await install_authorization(runtime_case, authorize_personal_grant(runtime_case.grant.model_copy(update={"access_token": SecretStr("replacement-token")})))
        current = runtime_case
    else:
        target = await runtime_case.store.resolve(runtime_case.query)
        await runtime_case.store.reject_authorization(RejectPersonalAuthorization(key=runtime_case.query.key, expected_connection_revision=target.authorization_revision))
        current = runtime_case
    runtime = McpPersonalToolRuntime(execution.contexts, current.bundle.personal_tool_access, execution.transport, lambda: current.query.now, "https://workspace.example")
    provider = await provider_for(replace(execution, case=current, runtime=runtime), PermitAllConnectorInvocationPolicy(), InvocationLog())
    public = FastMCP("personal-recovery", providers=[provider], middleware=[PersonalDiscoveryMiddleware(provider), AuthMiddleware(auth=personal_tool_permission_check(lambda context: True)), PersonalToolReservationMiddleware(provider)])
    token = set_request_connector_scope(connector_scope)
    try:
        async with Client(public) as client:
            tools = await client.list_tools()
            assert len(tools) == 1
            assert tools[0].name == ("read" if connector_scope else "Personal_read")
            assert tools[0].input_schema == before.parameters
            assert tools[0].description == before.description
            result = await client.call_tool_mcp(tools[0].name, {"value": "same"})
    finally:
        reset_request_connector_scope(token)
    assert result.is_error is True
    assert result.structured_content is None
    message = result.content[0].text
    assert "https://workspace.example/connectors?connector=downstream_mcp%3Apersonal" in message
    if authorization_state == "inventory_stale":
        assert "load tools" in message
        assert "Sign in again" not in message
    else:
        assert "Sign in again" in message
    assert "rediscover" in message
    assert "Do not automatically replay" in message
    if authorization_state == "rejected":
        assert "Inspect its outcome before retrying a write" in message
    assert "owner-token" not in message
    assert runtime_case.query.key.principal.subject not in message
    assert execution.transport.calls == []


@pytest.mark.asyncio
async def test_code_mode_preserves_recovery_guidance_in_failed_nested_call(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    current = replace(runtime_case, query=runtime_case.query.model_copy(update={"now": runtime_case.query.now + timedelta(days=1)}))
    runtime = McpPersonalToolRuntime(execution.contexts, current.bundle.personal_tool_access, execution.transport, lambda: current.query.now, "https://workspace.example")
    provider = await provider_for(replace(execution, case=current, runtime=runtime), PermitAllConnectorInvocationPolicy(), InvocationLog())
    result = await FastMcpMontyCodeModeAdapter(5).execute('Personal_read(value="same")', ProviderGateway(provider), UnrestrictedConnectorTools(), RejectingOpenApiExecutor())
    assert result.outcome == "failure"
    assert len(result.nested_calls) == 1
    call = result.nested_calls[0]
    assert isinstance(call, FailedNestedConnectorCall)
    assert "https://workspace.example/connectors?connector=downstream_mcp%3Apersonal" in call.error
    assert "Sign in again" in call.error
    assert "owner-token" not in call.error
    assert execution.transport.calls == []


@pytest.mark.parametrize("origin", ("https://workspace.example", "http://localhost:3010", "http://127.0.0.1:3010", "http://[::1]:3010"))
def test_recovery_origin_accepts_trusted_https_and_loopback(origin: str) -> None:
    assert validate_recovery_origin(origin + "/") == origin


@pytest.mark.parametrize("origin", ("", "http://workspace.example", "https://user:secret@workspace.example", "https://workspace.example/path", "https://workspace.example?next=evil", "https://workspace.example#evil", "https://workspace.example\\evil", "https://workspace.example\n", "//evil.example"))
def test_recovery_origin_rejects_unsafe_destinations(origin: str) -> None:
    with pytest.raises(ValueError):
        validate_recovery_origin(origin)


def test_recovery_selector_is_encoded_as_data() -> None:
    from umbod.core.connectors.downstream_mcp.personal.tools.runtime_models import PersonalAuthorizationRequired
    from umbod.mcp.connectors.downstream_mcp.personal_recovery import personal_authorization_failure

    result = personal_authorization_failure("https://workspace.example", "private&next=https://evil.example/#fragment", PersonalAuthorizationRequired("expired"))
    message = result.result["content"][0]["text"]
    destination = message.split("Open ", 1)[1].split(" ", 1)[0]
    parsed = urlsplit(destination)
    assert parsed.netloc == "workspace.example"
    assert parsed.path == "/connectors"
    assert parsed.fragment == ""
    assert parse_qs(parsed.query) == {"connector": ["downstream_mcp:private&next=https://evil.example/#fragment"]}
