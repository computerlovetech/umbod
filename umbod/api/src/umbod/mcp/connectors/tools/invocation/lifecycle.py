from dataclasses import dataclass

from umbod.mcp.logging import ConnectorToolInvocationLogger, McpToolIdentity, McpToolInvocationCompleted
from umbod.mcp.tools.invocation.lifecycle import McpToolInvocationLifecycle


@dataclass(frozen=True)
class ConnectorToolInvocationIdentity:
    tool_name: str
    connector_id: str
    connector_name: str
    operation_name: str

    def normalized(self) -> McpToolIdentity:
        normalized_connector_id = self.connector_id.strip()[:256] or "unknown"
        normalized_name = self.connector_name.strip()[:256] or normalized_connector_id
        return McpToolIdentity(
            tool_name=self.tool_name,
            connector_id=normalized_connector_id,
            connector_name=normalized_name,
            operation_name=self.operation_name,
        )


ConnectorInvocationLifecycle = McpToolInvocationLifecycle


def safely_record_invocation(logger_port: ConnectorToolInvocationLogger, completed: McpToolInvocationCompleted) -> None:
    try:
        logger_port.record_tool_invocation_completed(completed)
    except Exception:
        return
