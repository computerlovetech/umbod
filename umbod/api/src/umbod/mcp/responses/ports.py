from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from fastmcp.tools import ToolResult


ToolInvocation = Callable[[dict[str, Any]], Awaitable[ToolResult]]


class ToolResponseAdapter(Protocol):
    async def invoke(self, invocation: ToolInvocation, arguments: dict[str, Any]) -> ToolResult: ...

    def prepare(self, result: ToolResult, arguments: dict[str, Any]) -> ToolResult: ...

    def completed(self) -> None: ...
