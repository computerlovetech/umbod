from collections.abc import Mapping
from typing import Any, Protocol

from fastmcp.tools import ToolResult


class ConnectorToolInvoker(Protocol):
    async def invoke(self, arguments: Mapping[str, Any]) -> ToolResult: ...
