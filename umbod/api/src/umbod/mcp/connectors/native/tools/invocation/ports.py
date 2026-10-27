from collections.abc import Mapping
from typing import Any, Protocol

from fastmcp.tools import ToolResult

from umbod.core.capabilities import CapabilityIdentity


class NativeToolExecutionAdmission(Protocol):
    async def __call__(self, identity: CapabilityIdentity) -> None: ...


class ConnectorToolInvoker(Protocol):
    async def invoke(self, arguments: Mapping[str, Any]) -> ToolResult: ...
