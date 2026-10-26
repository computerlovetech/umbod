from typing import Annotated

from umbod.mcp.tools.registration import McpObservedToolRegistrar

from collections.abc import Sequence

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_server
from fastmcp.server.transforms import Transform
from fastmcp.tools import Tool
from pydantic import Field

from umbod.mcp.connectors.native.tools.discovery.manifest import (
    ConnectorCapabilityManifestFormatter,
    ConnectorCapabilityManifestService,
)
from umbod.core.callers import GroupMembership
from umbod.core.connectors.openapi.catalog import (
    PersistedAuthorizedOpenApiCapabilityCatalog,
)
from umbod.mcp.connectors.native.tools.discovery.openapi import (
    NormalizedOpenApiConnectorDiscovery,
    OpenApiConnectorDiscovery,
)
from umbod.mcp.connectors.native.tools.discovery.search import (
    ConnectorToolSearchInput,
    ConnectorToolSearchOutput,
)
from umbod.mcp.connectors.native.tools.infrastructure.dependencies import (
    get_allowed_connector_tool_refs,
    get_connector_tool_registry,
    get_connector_tool_search,
)
from umbod.mcp.connectors.openapi import (
    capture_openapi_groups,
    get_group_permission_reader,
    get_openapi_connector_store,
    openapi_availability_reader,
)

SearchQuery = Annotated[str, Field(description="Text used to find accessible connector tools.")]
SearchLimit = Annotated[
    int, Field(default=10, description="Maximum number of connector tools to return.")
]
ConnectorIds = Annotated[
    tuple[str, ...],
    Field(
        default=(),
        description=(
            "Optional connector IDs from the capability manifest used to narrow search results."
        ),
    ),
]
_SCOPE_DESCRIPTION = (
    " Use connector_ids to narrow results to connector IDs represented by the capability manifest."
)


async def search_tools(
    query: SearchQuery,
    limit: SearchLimit,
    connector_ids: ConnectorIds,
) -> ConnectorToolSearchOutput:
    server = get_server()
    groups = (
        capture_openapi_groups(server)
        if getattr(server, "include_openapi_in_connector_search", False)
        else GroupMembership(group_ids=())
    )
    search = get_connector_tool_search()
    registry = get_connector_tool_registry()
    allowed_tool_refs = get_allowed_connector_tool_refs()
    candidates = await registry.eligible_search_candidates(allowed_tool_refs)
    if getattr(server, "include_openapi_in_connector_search", False):
        candidates.extend(
            (
                await (await _openapi_discovery(server, groups)).search(query)
            ).candidates
        )
    return search.search(
        ConnectorToolSearchInput(
            query=query,
            limit=limit,
            connector_ids=connector_ids,
            candidates=candidates,
        )
    )


async def _openapi_discovery(server: FastMCP, groups: GroupMembership) -> OpenApiConnectorDiscovery:
    store = await get_openapi_connector_store(server)
    catalog = PersistedAuthorizedOpenApiCapabilityCatalog(
        store,
        await get_group_permission_reader(server),
        groups.group_ids,
        openapi_availability_reader(server, store),
        server.capability_description_overrides,
    )
    return NormalizedOpenApiConnectorDiscovery(catalog)


class ConnectorSearchManifestTransform(Transform):
    def __init__(self, base_description: str, character_budget: int) -> None:
        self._base_description = base_description
        self._manifest_service = ConnectorCapabilityManifestService()
        self._formatter = ConnectorCapabilityManifestFormatter(character_budget)

    async def list_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]:
        server = get_server()
        groups = (
            capture_openapi_groups(server)
            if getattr(server, "include_openapi_in_connector_search", False)
            else GroupMembership(group_ids=())
        )
        registry = get_connector_tool_registry()
        authorization_scope = get_allowed_connector_tool_refs()
        candidates = await registry.eligible_search_candidates(authorization_scope)
        if getattr(server, "include_openapi_in_connector_search", False):
            candidates.extend(
                (
                    await (await _openapi_discovery(server, groups)).enumerate()
                ).candidates
            )
        manifest = self._manifest_service.derive(candidates)
        description = self._formatter.format(self._base_description, manifest)
        return tuple(
            tool.model_copy(update={"description": description})
            if tool.name == "search_tools"
            else tool
            for tool in tools
        )


def register_connector_search_tool(mcp: FastMCP, description: str, registrar: McpObservedToolRegistrar) -> None:
    scoped_description = f"{description}{_SCOPE_DESCRIPTION}"
    registrar.register(
        search_tools,
        auth=None,
        name="search_tools",
        description=scoped_description,
        tags={"connectors", "gateway"},
        meta={"version": "1.0.0"},
    )
    mcp.add_transform(ConnectorSearchManifestTransform(scoped_description, 1000))
