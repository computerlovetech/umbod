from fastmcp.server.auth import AuthContext

from umbod.core.agent_behaviour import CallerNotAuthorized
from umbod.core.agent_behaviour.policy import validate_caller
from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE

from .caller import DiagnosticCallerCapture


class DiagnosticCallerPolicy:
    def __init__(self, callers: DiagnosticCallerCapture, allow_local: bool) -> None:
        self._callers = callers
        self._allow_local = allow_local

    def require(self) -> CallerContext:
        if _REQUEST_CONNECTOR_SCOPE.get():
            raise CallerNotAuthorized()
        caller = self._callers.capture()
        validate_caller(caller)
        if not self._allow_local and caller.authentication in {
            AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.LOCAL_SIMULATION,
        }:
            raise CallerNotAuthorized()
        return caller

    def authorize(self, context: AuthContext) -> bool:
        try:
            self.require()
        except CallerNotAuthorized:
            return False
        return True
