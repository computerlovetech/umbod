from typing import Protocol

from umbod.mcp.metrics import McpMetricsRecorder, McpProtocolMetricsRecorder


class McpApplicationMetricsRecorder(McpMetricsRecorder, McpProtocolMetricsRecorder, Protocol):
    pass


class McpMetricsServer(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class McpMetricsServerFactory(Protocol):
    def create(self) -> McpMetricsServer: ...
