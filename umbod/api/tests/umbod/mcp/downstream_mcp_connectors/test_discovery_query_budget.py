import pytest
from fastmcp import Client, FastMCP

from tests.umbod.mcp.downstream_mcp_connectors.discovery_query_support import discovery_query_case
from umbod.mcp.connectors.downstream_mcp.personal_runtime import PersonalToolReservationMiddleware


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_count", (1, 40))
async def test_tool_listing_definition_scans_do_not_scale_with_tool_count(tool_count: int) -> None:
    case = await discovery_query_case(tool_count)
    public = FastMCP("discovery-budget", providers=[case.provider], middleware=[PersonalToolReservationMiddleware(case.provider)])
    async with Client(public) as client:
        case.definitions.reset_mock()
        tools = await client.list_tools()
    assert len(tools) == tool_count
    case.definitions.list.assert_not_called()
    case.definitions.get.assert_not_called()
    case.catalogs.get.assert_not_called()
    case.credentials.get.assert_not_called()
    case.clients.create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_count", (1, 40))
@pytest.mark.parametrize("discovery", ("list", "search"))
async def test_initialized_discovery_never_reads_catalog_or_credentials(tool_count: int, discovery: str) -> None:
    case = await discovery_query_case(tool_count)
    if discovery == "list":
        tools = await case.provider.list_tools()
    else:
        tools = await case.provider.eligible_search_candidates()
    assert len(tools) == tool_count
    case.catalogs.get.assert_not_called()
    case.credentials.get.assert_not_called()
    case.definitions.list.assert_not_called()
    case.definitions.get.assert_not_called()
    case.publishing.is_published.assert_not_called()
    case.clients.create.assert_not_called()
