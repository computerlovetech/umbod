from datetime import datetime, timedelta, timezone

import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport


@pytest.mark.asyncio
async def test_expiry_is_checked_before_network(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    expired = target.model_copy(update={"expires_at": datetime.now(timezone.utc)})
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(expired)
    assert network.connections == []


@pytest.mark.asyncio
async def test_dns_and_connect_share_operation_deadline(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.delay = 2
    transport = make_transport(limits.model_copy(update={"operation_timeout_seconds": 0.05}), network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target)


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{"content-encoding": "gzip"}, {"content-length": "9999999"}])
async def test_compression_and_declared_oversize_rejected(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, headers: dict[str, str]) -> None:
    network.response_headers = headers
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_limits", [{"maximum_request_bytes": 1}, {"maximum_response_bytes": 1}, {"maximum_total_bytes": 1}])
async def test_wire_byte_limits(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, changed_limits: dict[str, int]) -> None:
    transport = make_transport(limits.model_copy(update=changed_limits), network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target)


@pytest.mark.asyncio
async def test_repeated_pagination_cursor_rejected(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.tools = []
    network.next_cursor = "repeat"
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target)
    assert len([body for _, _, body in network.requests if body.get("method") == "tools/list"]) == 2


@pytest.mark.asyncio
async def test_inventory_total_bound(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.tools = [{"name": f"tool-{index}", "inputSchema": {}} for index in range(257)]
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target)


@pytest.mark.asyncio
async def test_output_schema_present_variant(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.tools[0]["outputSchema"] = {"type": "object"}
    transport = make_transport(limits, network, ScriptedResolver())
    inventory = await transport.list_tools(target)
    assert inventory.tools[0].output_schema_status == "present"


@pytest.mark.asyncio
async def test_unique_pagination_is_bounded(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.tools = []
    network.cursor_sequence = ["one", "two", "three", "four"]
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target)
    assert len([body for _, _, body in network.requests if body.get("method") == "tools/list"]) == 3


@pytest.mark.asyncio
async def test_expiry_while_waiting_is_bounded(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.tool_delay = 1
    expires = target.model_copy(update={"expires_at": datetime.now(timezone.utc) + timedelta(seconds=0.15)})
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(expires)
