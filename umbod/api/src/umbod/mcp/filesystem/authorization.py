from fastmcp.server.auth import AuthContext

from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE


def root_filesystem_tool_access(_context: AuthContext) -> bool:
    return not _REQUEST_CONNECTOR_SCOPE.get()
