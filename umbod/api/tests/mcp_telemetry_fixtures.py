from umbod.mcp.logging import McpAuditEvent
from umbod.mcp.metrics import CompletedProtocolRequest, CompletedToolInvocation, InMemoryMcpMetricsRecorder, SuccessfulToolsList, ToolInvocationMetricIdentity
from umbod.mcp.telemetry import McpApplicationMetricsRecorder, McpMetricsServer, McpMetricsServerFactory


class RecordingApplicationMetricsRecorder(McpApplicationMetricsRecorder):
    def __init__(self) -> None:
        self.aggregation = InMemoryMcpMetricsRecorder()
        self.invocations: list[CompletedToolInvocation] = []
        self.protocol_requests: list[CompletedProtocolRequest] = []
        self.tools_lists: list[SuccessfulToolsList] = []

    def initialize_invocation(self, identity: ToolInvocationMetricIdentity) -> None:
        self.aggregation.initialize_invocation(identity)

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        self.invocations.append(invocation)
        self.aggregation.record_completed_invocation(invocation)

    def record_protocol_request(self, observation: CompletedProtocolRequest) -> None:
        self.protocol_requests.append(observation)

    def record_tools_list(self, observation: SuccessfulToolsList) -> None:
        self.tools_lists.append(observation)


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class RecordingMetricsServer(McpMetricsServer):
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0

    async def start(self) -> None:
        self.starts += 1

    async def stop(self) -> None:
        self.stops += 1


class RecordingMetricsServerFactory(McpMetricsServerFactory):
    def __init__(self) -> None:
        self.servers: list[RecordingMetricsServer] = []

    def create(self) -> RecordingMetricsServer:
        server = RecordingMetricsServer()
        self.servers.append(server)
        return server
