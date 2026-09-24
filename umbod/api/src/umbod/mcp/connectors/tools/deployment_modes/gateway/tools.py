from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.tools import ToolResult
from pydantic import Field

from umbod.mcp.connectors.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
)
from umbod.mcp.connectors.tools.infrastructure.dependencies import (
    get_allowed_connector_tool_refs,
    get_connector_tool_registry,
)
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry

ExecuteToolName = Annotated[
    str, Field(description="Generated flat-mode name of the connector tool to execute.")
]
ExecuteArguments = Annotated[
    dict[str, Any], Field(description="Arguments passed to the connector tool.")
]
GATEWAY_SEARCH_DESCRIPTION = (
    "Search connector tools currently accessible to the authenticated user."
)


async def execute_tool(
    tool_name: ExecuteToolName,
    arguments: ExecuteArguments,
    registry: RuntimeConnectorToolRegistry = Depends(get_connector_tool_registry),
    allowed_tool_refs: ConnectorToolAuthorizationScope = Depends(get_allowed_connector_tool_refs),
) -> ToolResult:
    return await registry.execute_tool(tool_name, arguments, allowed_tool_refs)


def register_connector_execute_tool(mcp: FastMCP) -> None:
    mcp.tool(
        name="execute_tool",
        description="Execute an accessible connector tool by its generated flat-mode name.",
        tags={"connectors", "gateway"},
        meta={"version": "1.0.0"},
    )(execute_tool)
