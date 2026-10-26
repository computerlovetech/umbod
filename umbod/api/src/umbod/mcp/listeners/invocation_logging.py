from umbod.mcp.logging.invocation.sink import McpToolInvocationLogSink
from umbod.mcp.signals.events import McpToolInvocationCompleted


class InvocationLoggingReceiver:
    def __init__(self, sink: McpToolInvocationLogSink) -> None:
        self._sink = sink

    def __call__(self, event: McpToolInvocationCompleted) -> None:
        self._sink.record_invocation_completed(event)
