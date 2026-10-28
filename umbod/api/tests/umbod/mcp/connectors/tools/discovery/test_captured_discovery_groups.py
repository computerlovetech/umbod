from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp.server.auth import AccessToken
from fastmcp.tools import Tool

from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema,
    CapabilityIdentity,
    NormalizedCapability,
)
from umbod.core.permissions.domain import GroupPermissionSet
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.connectors.openapi import deps
from umbod.mcp.connectors.native.tools.discovery import tools
from umbod.mcp.connectors.native.tools.discovery.search import (
    ConnectorToolSearchCandidate,
    InMemoryFuzzyConnectorToolSearch,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["search", "manifest"])
async def test_discovery_captures_openapi_groups_before_native_discovery_await(
    monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    token = AccessToken(token="secret", client_id="client", scopes=[], claims={"groups": ["original"]})
    monkeypatch.setattr(deps, "get_access_token", lambda: token)
    authorization_scope = object()
    observed_scopes: list[object] = []

    async def eligible_search_candidates(scope: object) -> list[ConnectorToolSearchCandidate]:
        observed_scopes.append(scope)
        token.claims["groups"] = ["replacement"]
        return []

    registry = SimpleNamespace(eligible_search_candidates=eligible_search_candidates)
    monkeypatch.setattr(tools, "get_connector_tool_registry", lambda: registry)
    monkeypatch.setattr(tools, "get_allowed_connector_tool_refs", lambda: authorization_scope)
    monkeypatch.setattr(tools, "get_connector_tool_search", InMemoryFuzzyConnectorToolSearch)
    snapshot = (NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="openapi",
            connector_id="inventory",
            capability_kind="tool",
            capability_key="getItem",
        ),
        title="Inventory item",
        description="Read inventory",
        input_schema={"type": "object"},
        output_schema=AbsentCapabilityOutputSchema(status="absent"),
        connector_display_name="Inventory",
        connector_capability_description="Manage inventory",
        search_hints=(),
    ),)
    projection = SimpleNamespace(snapshot=lambda: snapshot)
    permission_groups: list[str] = []

    async def list_group_permissions(group_id: str) -> GroupPermissionSet:
        permission_groups.append(group_id)
        return GroupPermissionSet(
            group_id=group_id,
            connector_ids=("inventory",) if group_id == "original" else (),
            capabilities=(),
        )

    reader = AsyncMock(spec=GroupPermissionReader)
    reader.list_group_permissions.side_effect = list_group_permissions

    async def permissions_after_projection_change() -> GroupPermissionReader:
        projection.snapshot = lambda: ()
        token.claims["groups"] = ["replacement"]
        return reader

    server = SimpleNamespace(
        permission_group_claim="groups",
        include_openapi_in_connector_search=True,
        openapi_discovery_catalog=projection,
        group_permission_reader_factory=SimpleNamespace(create=permissions_after_projection_change),
    )
    monkeypatch.setattr(tools, "get_server", lambda: server)

    if operation == "search":
        result = await tools.search_tools("getItem", 10, ())
        assert [
            (match.connector_id, match.operation_name, match.tool_name)
            for match in result.matches
        ] == [("inventory", "getItem", "execute_openapi")]
    else:
        search_tool = Tool.from_function(tools.search_tools, name="search_tools", description="Search")
        result_tools = await tools.ConnectorSearchManifestTransform("Search", 1000).list_tools(
            (search_tool,)
        )
        assert "Inventory: Manage inventory (1 operations)" in result_tools[0].description

    assert permission_groups == ["original"]
    assert observed_scopes == [authorization_scope]
