from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp.server.auth import AccessToken

from umbod.mcp.connectors.openapi import deps
from umbod.mcp.connectors.native.tools.discovery import tools
from umbod.mcp.connectors.native.tools.discovery.search import InMemoryFuzzyConnectorToolSearch


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["search", "manifest"])
async def test_discovery_captures_openapi_groups_before_native_discovery_await(
    monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    token = AccessToken(token="secret", client_id="client", scopes=[], claims={"groups": ["original"]})
    monkeypatch.setattr(deps, "get_access_token", lambda: token)
    authorization_scope = object()
    observed_scopes: list[object] = []

    async def eligible_search_candidates(scope: object) -> list[object]:
        observed_scopes.append(scope)
        token.claims["groups"] = ["replacement"]
        return []

    registry = SimpleNamespace(eligible_search_candidates=eligible_search_candidates)
    monkeypatch.setattr(tools, "get_connector_tool_registry", lambda: registry)
    monkeypatch.setattr(tools, "get_allowed_connector_tool_refs", lambda: authorization_scope)
    monkeypatch.setattr(tools, "get_connector_tool_search", InMemoryFuzzyConnectorToolSearch)
    monkeypatch.setattr(tools, "get_server", lambda: SimpleNamespace(
        permission_group_claim="groups", include_openapi_in_connector_search=True,
        capability_description_overrides={},
    ))
    monkeypatch.setattr(tools, "get_openapi_connector_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(tools, "get_group_permission_reader", AsyncMock(return_value=object()))
    monkeypatch.setattr(tools, "openapi_availability_reader", lambda server, store: None)
    catalog = Mock(return_value=SimpleNamespace(list_capabilities=AsyncMock(return_value=())))
    monkeypatch.setattr(tools, "PersistedAuthorizedOpenApiCapabilityCatalog", catalog)

    if operation == "search":
        await tools.search_tools("query", 10, ())
    else:
        await tools.ConnectorSearchManifestTransform("Search", 1000).list_tools(())

    assert catalog.call_args.args[2] == ("original",)
    assert observed_scopes == [authorization_scope]
