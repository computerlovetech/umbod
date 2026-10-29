import asyncio

from collections.abc import Callable
from typing import Any, TypedDict, Unpack

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError, ValidationError
from fastmcp.tools import FunctionTool, ToolResult
from fastmcp.tools.base import Tool
from pydantic import PrivateAttr

from umbod.core.invocation.failure_evidence import (
    InvocationFailureEvidence,
    InvocationFailureOrigin,
    InvocationReturnedFailure,
    exception_evidence,
)
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory


def tool_result_is_error(result: ToolResult) -> bool:
    return result.is_error


class ObservedToolOptions(TypedDict, total=False):
    tags: set[str]
    meta: dict[str, Any]
    result_is_error: Callable[[ToolResult], bool]


class ObservedFunctionTool(Tool):
    _delegate: Tool = PrivateAttr()
    _publisher: McpInvocationPublisher = PrivateAttr()
    _result_is_error: Callable[[ToolResult], bool] = PrivateAttr()
    _operation_names: frozenset[str] = PrivateAttr()

    def __init__(
        self, delegate: Tool, publisher: McpInvocationPublisher,
        result_is_error: Callable[[ToolResult], bool],
        operation_names: frozenset[str],
    ) -> None:
        super().__init__(**{field: getattr(delegate, field) for field in Tool.model_fields})
        self._delegate = delegate
        self._publisher = publisher
        self._result_is_error = result_is_error
        self._operation_names = operation_names

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        operation = arguments.get("operation")
        operation_name = operation if isinstance(operation, str) and operation in self._operation_names else None
        try:
            lifecycle = self._publisher.start(McpToolIdentity(tool_name=self.name, connector_id=None, operation_name=operation_name))
        except Exception as error:
            self._publisher.report_failure("invocation.start", error)
            lifecycle = None
        try:
            result = await self._delegate.run(arguments)
        except (asyncio.CancelledError, AuthorizationError):
            raise
        except ValidationError as error:
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.VALIDATION, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            raise
        except Exception as error:
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            raise
        try:
            is_error = self._result_is_error(result)
        except Exception as error:
            self._publisher.report_failure("invocation.result_classification", error)
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            return result
        if is_error:
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, InvocationReturnedFailure(InvocationFailureOrigin.INTERNAL))
        else:
            self._publish_success(lifecycle)
        return result

    def _publish_success(self, lifecycle: Any) -> None:
        try:
            self._publisher.succeeded(lifecycle)
        except Exception as error:
            self._publisher.report_failure("invocation.success", error)

    def _publish_failure(self, lifecycle: Any, category: McpToolInvocationFailureCategory, evidence: InvocationFailureEvidence) -> None:
        try:
            self._publisher.failed(lifecycle, category, None, evidence)
        except Exception as error:
            self._publisher.report_failure("invocation.failure", error)


class McpObservedToolRegistrar:
    def __init__(self, mcp: FastMCP, publisher: McpInvocationPublisher) -> None:
        self._mcp = mcp
        self._publisher = publisher

    def register(
        self,
        fn: Callable[..., Any],
        *,
        name: str,
        description: str,
        auth: Any,
        **options: Unpack[ObservedToolOptions],
    ) -> ObservedFunctionTool:
        delegate = FunctionTool.from_function(
            fn, name=name, description=description, auth=auth,
            tags=options.get("tags", set()), meta=options.get("meta", {}),
        )
        return self.register_tool(
            delegate, result_is_error=options.get("result_is_error", tool_result_is_error),
            operation_names=frozenset(),
        )

    def register_tool(
        self, delegate: Tool, *,
        result_is_error: Callable[[ToolResult], bool],
        operation_names: frozenset[str],
    ) -> ObservedFunctionTool:
        tool = ObservedFunctionTool(delegate, self._publisher, result_is_error, operation_names)
        self._mcp.add_tool(tool)
        self._publisher.tool_registered(McpToolIdentity(tool_name=delegate.name, connector_id=None, operation_name=None))
        return tool
