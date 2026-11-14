from fastmcp.exceptions import ToolError

from umbod.core.capabilities.tools.names import mangle_public_tool_name


DIAGNOSTIC_TOOL_NAME = "report_diagnostic"


def connector_tool_name_available(prefix: str, operation: str) -> bool:
    return operation != DIAGNOSTIC_TOOL_NAME and mangle_public_tool_name(prefix, operation) != DIAGNOSTIC_TOOL_NAME


def ensure_connector_tool_name_available(prefix: str, operation: str) -> None:
    if not connector_tool_name_available(prefix, operation):
        raise ToolError("public_tool_name_conflict")
