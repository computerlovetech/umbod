from fastmcp.exceptions import ToolError

from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.mcp.portable_draft_names import PORTABLE_DRAFT_TOOL_NAMES


DIAGNOSTIC_TOOL_NAME = "report_diagnostic"
_RESERVED_BUILTIN_TOOL_NAMES = PORTABLE_DRAFT_TOOL_NAMES | {DIAGNOSTIC_TOOL_NAME}


def connector_tool_name_available(prefix: str, operation: str) -> bool:
    return not _RESERVED_BUILTIN_TOOL_NAMES.intersection({operation, mangle_public_tool_name(prefix, operation)})


def ensure_connector_tool_name_available(prefix: str, operation: str) -> None:
    if not connector_tool_name_available(prefix, operation):
        raise ToolError("public_tool_name_conflict")
