from collections.abc import Mapping

from fastmcp.server.dependencies import get_access_token


class JwtCurrentPrincipalGroups:
    def __init__(self, claim_name: str) -> None:
        self._claim_name = claim_name

    def subject(self) -> str:
        token = get_access_token()
        claims = getattr(token, 'claims', {}) if token is not None else {}
        subject = claims.get('sub') if isinstance(claims, Mapping) else None
        return subject if isinstance(subject, str) and subject else 'authenticated-principal'

    def groups(self) -> tuple[str, ...]:
        token = get_access_token()
        claims = getattr(token, 'claims', {}) if token is not None else {}
        if not isinstance(claims, Mapping):
            return ()
        value = claims.get(self._claim_name)
        if isinstance(value, str):
            return (value,) if value else ()
        if isinstance(value, (list, tuple)):
            return tuple(dict.fromkeys((group for group in value if isinstance(group, str) and group)))
        return ()
