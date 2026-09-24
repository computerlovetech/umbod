from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from fastmcp import Client, FastMCP

from umbod.mcp.settings import MCPAppSettings, MCPSettings
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolExposureMcpBuilder,
)


@dataclass(frozen=True)
class CodeExecution:
    outcome: str
    final_value: Any
    printed_output: str
    error: str | None
    nested_calls: Sequence[dict[str, Any]]


class ConnectorCodeModeDriver:
    def __init__(self, mcp: FastMCP) -> None:
        self._mcp = mcp

    async def list_tool_names(self) -> set[str]:
        async with Client(self._mcp) as client:
            return {tool.name for tool in await client.list_tools()}

    async def list_tool_descriptions(self) -> dict[str, str | None]:
        async with Client(self._mcp) as client:
            return {tool.name: tool.description for tool in await client.list_tools()}

    async def search(self, query: str) -> list[dict[str, Any]]:
        async with Client(self._mcp) as client:
            result = await client.call_tool("search_tools", {"query": query})
        return result.structured_content["matches"]

    async def execute(self, code: str) -> CodeExecution:
        async with Client(self._mcp) as client:
            result = await client.call_tool("execute_code", {"code": code}, raise_on_error=False)
        content = result.structured_content
        return CodeExecution(
            outcome=content["outcome"],
            final_value=content.get("final_value"),
            printed_output=content["printed_output"],
            error=content.get("error"),
            nested_calls=content["nested_calls"],
        )


class ConnectorCodeMode:
    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []
        self._operation: Callable[..., dict[str, Any]] = self._recording_operation

    async def running(self, timeout_seconds: float = 30.0) -> ConnectorCodeModeDriver:
        builder = ConnectorToolExposureMcpBuilder().with_operation(self._operation)
        builder._exposure_mode = "codemode"
        builder._code_execution_timeout_seconds = timeout_seconds
        return ConnectorCodeModeDriver(await builder.build())

    def startup_settings(self, timeout_seconds: float | None = None) -> MCPAppSettings:
        values: dict[str, Any] = {"connector_tool_exposure_mode": "codemode", "_env_file": None}
        if timeout_seconds is not None:
            values["connector_code_execution_timeout_seconds"] = timeout_seconds
        return MCPAppSettings(mcp=MCPSettings(**values), _env_file=None)

    def _recording_operation(self, limit: int) -> dict[str, Any]:
        arguments = {"limit": limit}
        self.invocations.append(arguments)
        return {"arguments": arguments}
