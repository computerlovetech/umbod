from umbod.core.connectors.openapi.stores import OpenApiConnectorReader
from umbod.mcp.metrics import InvocationScope, McpMetricsRecorder, ToolInvocationMetricIdentity
from umbod.mcp.tools.invocation.telemetry import initialize_invocation_metrics


async def initialize_openapi_metrics(
    reader: OpenApiConnectorReader, recorder: McpMetricsRecorder
) -> None:
    for connector in await reader.list_connectors():
        initialize_invocation_metrics(
            recorder,
            ToolInvocationMetricIdentity(
                scope=InvocationScope.CONNECTOR,
                connector_name=connector.connector_id,
                tool_name="execute_openapi",
            )
        )
