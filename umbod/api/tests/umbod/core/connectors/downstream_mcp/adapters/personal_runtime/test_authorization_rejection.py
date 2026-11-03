import asyncio

import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 500])
async def test_only_actual_resource_401_becomes_sanitized_typed_rejection(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, status: int) -> None:
    network.status = status
    network.response_headers = {"content-type": "invalid/header-sentinel", "www-authenticate": "header-sentinel", "location": "https://evil.example/body-sentinel"}
    network.call_result = {"secret": "body-sentinel"}
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await transport.list_tools(target)
    assert isinstance(caught.value, PersonalAuthorizationRejected) == (status == 401)
    assert caught.value.__context__ is None
    assert str(caught.value) == "Personal MCP unavailable"
    assert len(network.requests) == 1


@pytest.mark.asyncio
async def test_reflected_token_on_401_never_crosses_the_network_guard(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.status = 401
    network.response_headers = {"content-type": "alice-secret-token", "www-authenticate": "alice-secret-token"}
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await transport.list_tools(target)
    assert str(caught.value) == "Personal MCP unavailable"
    assert caught.value.__context__ is None


@pytest.mark.asyncio
async def test_cleanup_401_does_not_create_rejection(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.session = True
    network.cleanup_status = 401
    transport = make_transport(limits, network, ScriptedResolver())
    try:
        await transport.list_tools(target)
    except PersonalRuntimeUnavailable as error:
        assert not isinstance(error, PersonalAuthorizationRejected)
    assert any(request[0] == "DELETE" for request in network.requests)


@pytest.mark.asyncio
async def test_external_cancellation_is_not_rejection(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.delay = 30
    transport = make_transport(limits, network, ScriptedResolver())
    task = asyncio.create_task(transport.list_tools(target))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
