from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import CallerSnapshot, LegacyGroupClaimPolicy
from umbod.mcp.auth.membership import McpAccessTokenAvailability, capture_mcp_caller

from .ports import FilesystemGroupClaimFields


class CurrentFilesystemCallerCapture:
    def __init__(
        self,
        server: FastMCP,
        claim_fields: FilesystemGroupClaimFields,
    ) -> None:
        self._server = server
        self._claim_fields = claim_fields

    def capture(self) -> CallerSnapshot:
        return capture_mcp_caller(
            self._server, get_access_token() or McpAccessTokenAvailability.UNAVAILABLE, self._claim_fields.claim_fields(), LegacyGroupClaimPolicy.RUNTIME,
        )
