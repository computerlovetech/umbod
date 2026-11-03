from .contracts import LOOKUP_FINGERPRINT
import socket

import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 307, 401, 403, 500])
async def test_http_failures_never_redirect_refresh_or_reflect_secrets(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, status: int) -> None:
    network.status = status
    network.response_headers = {"location": "https://evil.example/body-sentinel", "www-authenticate": "Bearer header-sentinel"}
    network.call_result = {"secret": "body-sentinel"}
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await transport.list_tools(target)
    assert str(caught.value) == "Personal MCP unavailable"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert len(network.requests) == 1


@pytest.mark.asyncio
async def test_literal_access_token_echo_is_rejected(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.call_result = {"content": [{"type": "text", "text": target.access_token.get_secret_value()}]}
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable, match="^Personal MCP unavailable$"):
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {},
    {"resultType": "input_required", "inputRequests": {}, "requestState": "do-not-replay"},
    {"content": [], "resultType": "input_required"},
    {"content": [], "resultType": "claimed-extension"},
    {"content": [], "task": {"taskId": "do-not-poll"}},
    {"content": [], "unexpected": "do-not-accept"},
    {"content": [], "isError": "false"},
])
async def test_nonstandard_results_never_enter_consent_or_replay(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, payload: dict[str, object]) -> None:
    network.call_result = payload
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    methods = [body.get("method") for _, _, body in network.requests]
    assert methods.count("tools/call") == 1
    assert set(methods) <= {"initialize", "notifications/initialized", "tools/list", "tools/call"}


@pytest.mark.asyncio
async def test_call_never_fetches_advertised_external_output_schema(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, monkeypatch: pytest.MonkeyPatch) -> None:
    external_attempts: list[tuple[object, ...]] = []

    def deny_external_socket(*args: object, **kwargs: object) -> socket.socket:
        external_attempts.append(args)
        raise AssertionError("Unexpected schema network access")

    monkeypatch.setattr(socket, "create_connection", deny_external_socket)
    network.tools[0]["outputSchema"] = {"type": "object", "$ref": "http://127.0.0.1:9/private-schema"}
    network.call_result = {"content": [], "structuredContent": {"value": "complete"}}
    transport = make_transport(limits, network, ScriptedResolver())
    inventory = await transport.list_tools(target)
    assert inventory.tools[0].output_schema_status == "present"
    assert inventory.tools[0].output_schema == {"type": "object", "$ref": "http://127.0.0.1:9/private-schema"}
    explicit_listing_requests = len(network.requests)
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    methods = [body.get("method") for _, _, body in network.requests[explicit_listing_requests:]]
    assert methods.count("tools/list") == 1
    assert "tools/call" not in methods
    assert external_attempts == []
