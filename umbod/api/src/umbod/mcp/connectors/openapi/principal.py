from collections.abc import Mapping

from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import CallerContextProvider, SubjectIdentity
from umbod.mcp.auth.groups import capture_openapi_principal_groups


class JwtCurrentPrincipalGroups:
    def __init__(self, claim_name: str, callers: CallerContextProvider) -> None:
        self._claim_name = claim_name
        self._callers = callers

    def subject(self) -> str:
        subject = self._callers.get_context().subject
        return subject.subject if isinstance(subject, SubjectIdentity) and subject.subject else 'authenticated-principal'

    def groups(self) -> tuple[str, ...]:
        token = get_access_token()
        claims = getattr(token, 'claims', {}) if token is not None else {}
        if not isinstance(claims, Mapping):
            return ()
        return capture_openapi_principal_groups(claims, self._claim_name).group_ids
