import asyncio
from datetime import timedelta
from umbod.core.connectors.downstream_mcp.personal_connections.models import SetPersonalConnectionEnabled
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.owner_metadata_support import metadata_server

__all__ = ["runtime_case"]


async def _observe(public: FastMCP, subject: str, exposure: str) -> dict[str, Any]:
    identity = AuthenticatedUser(AccessToken(token=f"{subject}-upstream", client_id="metadata-client", scopes=[], claims={"sub": subject, "groups": ["team"]})) if subject else None
    marker = auth_context_var.set(identity)
    try:
        async with Client(public) as client:
            tools = await client.list_tools()
            if exposure == "flat":
                return {"tools": [tool.model_dump(mode="json") for tool in tools]}
            result = await client.call_tool("search_tools", {"query": "read"})
            return {"tools": [tool.model_dump(mode="json") for tool in tools], "search": result.structured_content}
    finally:
        auth_context_var.reset(marker)


def _assert_owner(observation: dict[str, Any], subject: str, exposure: str) -> None:
    if exposure == "flat":
        matches = observation["tools"]
        assert [tool["name"] for tool in matches] == ["Personal_read"]
        schema = matches[0]["input_schema"]
    else:
        matches = observation["search"]["matches"]
        assert [tool["tool_name"] for tool in matches] == ["Personal_read"]
        schema = matches[0]["input_schema"]
        search = next(tool for tool in observation["tools"] if tool["name"] == "search_tools")
        assert "Personal:" in search["description"]
        assert "1 operations" in search["description"]
    assert matches[0]["description"] == f"Private {subject} description"
    assert schema["properties"]["value"]["type"] == ("string" if subject == "owner" else "integer")


@pytest.mark.asyncio
@pytest.mark.parametrize("exposure", ("flat", "gateway", "codemode"))
async def test_wire_metadata_tracks_owner_a_b_a_without_cached_private_descriptors(runtime_case: RuntimeCase, exposure: str) -> None:
    public = await metadata_server(runtime_case, exposure)
    first = await _observe(public, "owner", exposure)
    second = await _observe(public, "bob", exposure)
    third = await _observe(public, "owner", exposure)
    _assert_owner(first, "owner", exposure)
    _assert_owner(second, "bob", exposure)
    _assert_owner(third, "owner", exposure)
    assert first == third


@pytest.mark.asyncio
@pytest.mark.parametrize("exposure", ("flat", "gateway", "codemode"))
async def test_concurrent_wire_metadata_is_owner_local_and_anonymous_has_no_inventory(runtime_case: RuntimeCase, exposure: str) -> None:
    public = await metadata_server(runtime_case, exposure)
    observations = await asyncio.gather(*(_observe(public, subject, exposure) for subject in ("owner", "bob", "", "no_inventory")))
    _assert_owner(observations[0], "owner", exposure)
    _assert_owner(observations[1], "bob", exposure)
    for observation in observations[2:]:
        if exposure == "flat":
            assert observation["tools"] == []
        else:
            assert observation["search"]["matches"] == []
            search = next(tool for tool in observation["tools"] if tool["name"] == "search_tools")
            assert "Personal:" not in search["description"]
        assert "Private owner description" not in str(observation)
        assert "Private bob description" not in str(observation)


@pytest.mark.asyncio
@pytest.mark.parametrize("exposure", ("flat", "gateway", "codemode"))
@pytest.mark.parametrize("change", ("disable", "expiry"))
async def test_later_public_discovery_rechecks_owner_availability(runtime_case: RuntimeCase, exposure: str, change: str) -> None:
    public = await metadata_server(runtime_case, exposure)
    _assert_owner(await _observe(public, "owner", exposure), "owner", exposure)
    if change == "disable":
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
    else:
        async with public.downstream_mcp_tool_provider.discovery_operation() as operation:
            operation.owner.clock = lambda: runtime_case.query.now + timedelta(days=1)
    observation = await _observe(public, "owner", exposure)
    if exposure == "flat":
        assert observation["tools"] == []
    else:
        assert observation["search"]["matches"] == []
    assert "Private owner description" not in str(observation)
    if change == "disable":
        _assert_owner(await _observe(public, "bob", exposure), "bob", exposure)
