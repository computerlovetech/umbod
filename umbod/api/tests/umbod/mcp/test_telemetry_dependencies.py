import pytest

from tests.mcp_telemetry_fixtures import RecordingApplicationMetricsRecorder, RecordingAuditSink, RecordingMetricsServerFactory
from umbod.mcp.logging import McpAuditRecorder
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.metrics import CompletedProtocolRequest, CompletedToolInvocation, InvocationOutcome, InvocationScope, ProtocolMethod, ProtocolOutcome, SuccessfulToolsList
from umbod.mcp.telemetry import McpTelemetryDependencies


@pytest.mark.asyncio
async def test_telemetry_bundle_accepts_in_memory_metrics_and_fresh_listeners() -> None:
    metrics = RecordingApplicationMetricsRecorder()
    listeners = RecordingMetricsServerFactory()
    telemetry = McpTelemetryDependencies(InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter()), McpAuditRecorder(RecordingAuditSink(), "test"), metrics, listeners)
    completion = CompletedToolInvocation(scope=InvocationScope.REQUEST, connector_name="internal", tool_name="read", outcome=InvocationOutcome.SUCCESS, duration_seconds=0.125)
    telemetry.metrics_recorder.record_completed_invocation(completion)
    protocol = CompletedProtocolRequest(method=ProtocolMethod.LIST_TOOLS, outcome=ProtocolOutcome.SUCCESS, duration_seconds=0.25)
    listing = SuccessfulToolsList(tool_count=3)
    telemetry.metrics_recorder.record_protocol_request(protocol)
    telemetry.metrics_recorder.record_tools_list(listing)
    first = telemetry.metrics_server_factory.create()
    second = telemetry.metrics_server_factory.create()
    await first.start()
    await first.stop()
    assert metrics.invocations == [completion]
    assert metrics.protocol_requests == [protocol]
    assert metrics.tools_lists == [listing]
    assert any(sample.value == 1 for sample in metrics.aggregation.metric_samples())
    assert first is not second
    assert [(server.starts, server.stops) for server in listeners.servers] == [(1, 1), (0, 0)]
