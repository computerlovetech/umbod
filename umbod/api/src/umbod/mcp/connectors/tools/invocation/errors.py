from fastmcp.tools import ToolResult
from mcp.types import CallToolResult


class ConnectorToolErrorFormatter:
    def format_error(self, connector_id: str, operation_name: str, error: Exception) -> str:
        connector_name = connector_id.replace("_", " ").title()
        return f"The {connector_name} {operation_name} tool could not complete: {error}"


class ConnectorToolFailureResult(ToolResult):
    def to_mcp_result(self) -> CallToolResult:
        return CallToolResult(
            content=self.content, structured_content=self.structured_content, is_error=True
        )
