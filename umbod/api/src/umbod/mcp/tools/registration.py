import asyncio
import logging

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError, ValidationError
from fastmcp.tools import FunctionTool, ToolResult
from fastmcp.tools.base import Tool
from pydantic import PrivateAttr

from umbod.mcp.logging import McpToolIdentity, McpToolInvocationFailureCategory
from umbod.mcp.tools.invocation.telemetry import McpToolInvocationObserver

logger = logging.getLogger(__name__)


class ObservedFunctionTool(Tool):
    _delegate: FunctionTool = PrivateAttr()
    _observer: McpToolInvocationObserver = PrivateAttr()

    def __init__(self, delegate: FunctionTool, observer: McpToolInvocationObserver) -> None:
        super().__init__(**{field: getattr(delegate, field) for field in Tool.model_fields})
        self._delegate = delegate
        self._observer = observer

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            lifecycle = self._observer.start(McpToolIdentity(tool_name=self.name, connector_id=None, operation_name=None))
        except Exception:
            logger.error("MCP tool invocation observation start failed")
            lifecycle = None
        try:
            result = await self._delegate.run(arguments)
        except (asyncio.CancelledError, AuthorizationError):
            raise
        except ValidationError:
            self._safely_fail(lifecycle, McpToolInvocationFailureCategory.VALIDATION)
            raise
        except Exception:
            self._safely_fail(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR)
            raise
        try:
            is_error = result.is_error
        except Exception:
            logger.error("MCP tool result classification failed")
            self._safely_fail(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR)
            return result
        if is_error:
            self._safely_fail(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR)
        else:
            self._safely_succeed(lifecycle)
        return result

    def _safely_succeed(self, lifecycle: Any) -> None:
        try:
            self._observer.succeeded(lifecycle)
        except Exception:
            logger.error("MCP tool invocation success observation failed")

    def _safely_fail(self, lifecycle: Any, category: McpToolInvocationFailureCategory) -> None:
        try:
            self._observer.failed(lifecycle, category)
        except Exception:
            logger.error("MCP tool invocation failure observation failed")


class McpObservedToolRegistrar:
    def __init__(self, mcp: FastMCP, observer: McpToolInvocationObserver) -> None:
        self._mcp = mcp
        self._observer = observer

    def register(
        self,
        fn: Callable[..., Any],
        *,
        name: str,
        description: str,
        auth: Any,
    ) -> ObservedFunctionTool:
        delegate = FunctionTool.from_function(fn, name=name, description=description, auth=auth)
        tool = ObservedFunctionTool(delegate, self._observer)
        self._mcp.add_tool(tool)
        return tool
