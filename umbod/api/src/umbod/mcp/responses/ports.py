from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from fastmcp.tools import ToolResult


ToolInvocation = Callable[[dict[str, Any]], Awaitable[ToolResult]]


class ToolResponseAdapter(Protocol):
    def invocation_context(self) -> AbstractContextManager[None]: ...

    def prepare(self, result: ToolResult, arguments: dict[str, Any]) -> ToolResult: ...

    def prepare_failure(self, error: Exception, arguments: dict[str, Any]) -> ToolResult | None: ...

    def completed(self) -> None: ...
