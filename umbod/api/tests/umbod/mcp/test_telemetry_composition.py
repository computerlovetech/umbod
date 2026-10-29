import httpx
import pytest

from umbod.mcp.metrics import CompletedToolInvocation, InvocationOutcome, InvocationScope
from umbod.mcp.metrics.http_server import create_metrics_app
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.telemetry.composition import ConfiguredMcpMetricsServerFactory, create_configured_mcp_telemetry


@pytest.mark.asyncio
async def test_configured_applications_export_only_their_own_metrics_from_bound_recorder() -> None:
    settings = MCPAppSettings(mcp={"metrics_port": 9123})
    first = create_configured_mcp_telemetry(settings)
    second = create_configured_mcp_telemetry(settings)
    first.metrics_recorder.record_completed_invocation(CompletedToolInvocation(scope=InvocationScope.CONNECTOR, connector_name="inventory", tool_name="read_items", outcome=InvocationOutcome.SUCCESS, duration_seconds=0.125))
    assert first.metrics_recorder is not second.metrics_recorder
    assert first.invocation_log_sink is not second.invocation_log_sink
    assert first.audit_recorder is not second.audit_recorder
    for telemetry, expected in ((first, True), (second, False)):
        factory = telemetry.metrics_server_factory
        assert isinstance(factory, ConfiguredMcpMetricsServerFactory)
        assert factory.recorder is telemetry.metrics_recorder
        assert factory.host == "0.0.0.0"
        assert factory.port == 9123
        assert factory.create() is not factory.create()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(create_metrics_app(factory.recorder)), base_url="http://test") as client:
            response = await client.get("/metrics")
        assert response.status_code == 200
        assert ('umbod_mcp_tool_invocations_total{connector_name="inventory",outcome="success",tool_name="read_items"} 1.0' in response.text) is expected
        assert ('umbod_mcp_tool_invocation_duration_seconds_sum{connector_name="inventory",outcome="success",tool_name="read_items"} 0.125' in response.text) is expected
