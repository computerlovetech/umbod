from typing import Annotated

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP
from fastmcp.server.dependencies import get_server
from fastmcp.tools import ToolResult
from pydantic import Field, JsonValue

from umbod.mcp.connectors.tools.deployment_modes.codemode.sandbox import (
    FastMcpMontyCodeModeAdapter,
    OpenApiCodeModeExecutor,
    OpenApiCodeModeInvocation,
)
from umbod.mcp.connectors.tools.infrastructure.dependencies import (
    get_allowed_connector_tool_refs,
    get_connector_tool_registry,
)
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry

CodeInput = Annotated[
    str,
    Field(
        description="Python code that composes accessible connector tools by generated flat name."
    ),
]

CODEMODE_SEARCH_DESCRIPTION = (
    "Search for connector tools available to the current user. Use this before answering or acting "
    "whenever a request may require an external service, account, business system, live data, or an "
    "unfamiliar capability. Available connectors may support data retrieval, communication, scheduling, "
    "documents, project management, CRM, travel, and other configured integrations. Search by the user's "
    "goal and domain instead of guessing tool names. Results include executable tool names and input schemas."
)
CODEMODE_EXECUTE_DESCRIPTION = (
    "Execute sandboxed Python using accessible connector tools and the controlled execute_openapi function. "
    "Call execute_openapi with keyword-only connector_id, operation_id, path, query, headers, and body JSON values. "
    "Body is always tagged: use {'state': 'missing'} when absent and {'state': 'present', 'value': value} "
    "when present; an empty JSON object is {'state': 'present', 'value': {}} and is not missing. "
    "Before OpenAPI calls, use search_tools to discover the operation and its complete input schema. "
    "Before writing code, use search_tools to "
    "discover required tool names and schemas unless they were already returned in this conversation. Use "
    "returned tool_name values as functions and follow each input_schema. Search again when a required "
    "capability or argument is unclear."
)


class UnavailableOpenApiCodeModeExecutor:
    async def __call__(self, invocation: OpenApiCodeModeInvocation) -> JsonValue:
        raise RuntimeError("OpenAPI execution is unavailable")


def get_openapi_codemode_executor(
    server: Annotated[FastMCP, CurrentFastMCP()],
) -> OpenApiCodeModeExecutor:
    try:
        executor = server.openapi_codemode_executor
    except AttributeError:
        return UnavailableOpenApiCodeModeExecutor()
    if callable(executor):
        return executor
    return UnavailableOpenApiCodeModeExecutor()


async def execute_code(
    code: CodeInput,
) -> ToolResult:
    registry = get_connector_tool_registry()
    allowed_tool_refs = get_allowed_connector_tool_refs()
    openapi_executor = get_openapi_codemode_executor(get_server())
    adapter: FastMcpMontyCodeModeAdapter = registry.code_mode_adapter
    result = await adapter.execute(code, registry, allowed_tool_refs, openapi_executor)
    return ToolResult(structured_content=result.model_dump(mode="json"))


def register_connector_code_mode_tool(
    mcp: FastMCP,
    registry: RuntimeConnectorToolRegistry,
    timeout_seconds: float,
) -> None:
    registry.code_mode_adapter = FastMcpMontyCodeModeAdapter(timeout_seconds)
    mcp.tool(
        name="execute_code",
        description=CODEMODE_EXECUTE_DESCRIPTION,
        tags={"connectors", "codemode"},
        meta={"version": "2.0.0"},
    )(execute_code)
