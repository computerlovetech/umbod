from typing import Protocol

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER, AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity, UnavailableIssuer
from umbod.mcp.auth.caller import authentication_provenance, caller_context_from_access_token


class DiagnosticCallerCapture(Protocol):
    def capture(self) -> CallerContext: ...


class CurrentDiagnosticCallerCapture:
    def __init__(self, server: FastMCP) -> None:
        self._server = server

    def capture(self) -> CallerContext:
        caller = caller_context_from_access_token(
            get_access_token(), authentication_provenance(self._server.auth),
        )
        subject = caller.subject
        if caller.authentication == AuthenticationProvenance.LOCAL_TEST and isinstance(subject, SubjectIdentity) and isinstance(subject.issuer, UnavailableIssuer):
            return CallerContext(authentication=caller.authentication, subject=SubjectIdentity(issuer=DeclaredIssuer(value=LOCAL_DEVELOPMENT_ISSUER), subject=subject.subject))
        return caller
