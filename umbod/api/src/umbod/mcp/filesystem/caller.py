from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import CallerSnapshot
from umbod.mcp.auth.caller import authentication_provenance, caller_context_from_access_token
from umbod.mcp.auth.groups import capture_runtime_permission_groups

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
        token = get_access_token()
        return CallerSnapshot(
            caller=caller_context_from_access_token(
                token, authentication_provenance(self._server.auth)
            ),
            groups=capture_runtime_permission_groups(
                token.claims if token else {}, self._claim_fields.claim_fields()
            ),
        )
