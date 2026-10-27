from typing import Protocol

from umbod.mcp.metrics.protocol_models import CompletedProtocolRequest, SuccessfulToolsList


class McpProtocolMetricsRecorder(Protocol):
    def record_protocol_request(self, observation: CompletedProtocolRequest) -> None: ...

    def record_tools_list(self, observation: SuccessfulToolsList) -> None: ...
