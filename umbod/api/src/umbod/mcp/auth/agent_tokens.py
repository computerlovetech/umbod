import json

from fastmcp.server.auth import AccessToken, AuthProvider, MultiAuth, TokenVerifier
from fastmcp.server.auth.auth import TokenVerificationError
from pydantic import Field, SecretStr

from umbod.core.agent_tokens import (
    AgentCredentialVerifier,
    InvalidAgentCredential,
    PublicMcpAgentIdentity,
    is_agent_credential_bearer,
)

_OAUTH_SOURCE = "umbod-public-oauth"
_AGENT_SOURCE = "umbod-public-agent"


class _PublicAgentAccessToken(AccessToken):
    identity: PublicMcpAgentIdentity = Field(exclude=True, repr=False, frozen=True)


class _PublicAgentVerifier(TokenVerifier):
    def __init__(self, verifier: AgentCredentialVerifier, required_scopes: list[str]) -> None:
        super().__init__(required_scopes=required_scopes)
        self._verifier = verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        if not is_agent_credential_bearer(token):
            return None
        try:
            identity = await self._verifier.verify_for_public_mcp(SecretStr(token))
        except InvalidAgentCredential:
            return None
        except Exception:
            raise TokenVerificationError("Agent credential verification unavailable") from None
        return _PublicAgentAccessToken(
            token="",
            client_id=identity.agent_id,
            scopes=list(self.required_scopes),
            identity=identity,
        )


class PublicAgentMultiAuth(MultiAuth):
    def __init__(self, oauth: AuthProvider, verifier: AgentCredentialVerifier) -> None:
        agent_verifiers = {_AGENT_SOURCE: _PublicAgentVerifier(verifier, oauth.required_scopes)}
        super().__init__(server=oauth, server_source_id=_OAUTH_SOURCE, verifiers=agent_verifiers)
        self._agent_only = MultiAuth(verifiers=agent_verifiers)

    async def verify_token(self, token: str) -> AccessToken | None:
        if is_agent_credential_bearer(token):
            return await self._agent_only.verify_token(token)
        return await super().verify_token(token)


def create_public_agent_auth(
    oauth: AuthProvider, verifier: AgentCredentialVerifier,
) -> PublicAgentMultiAuth:
    return PublicAgentMultiAuth(oauth, verifier)


def _qualified_source(provider: object, token: object) -> str | None:
    if type(provider) is not PublicAgentMultiAuth or not isinstance(token, AccessToken):
        return None
    try:
        components = json.loads(token.client_id)
    except (TypeError, ValueError, RecursionError):
        return None
    match components:
        case [str(source), str(), issuer, subject] if (
            (issuer is None or isinstance(issuer, str))
            and (subject is None or isinstance(subject, str))
        ):
            return source
        case _:
            return None


def verified_agent_identity(provider: object, token: object) -> PublicMcpAgentIdentity | None:
    if is_agent_access_token(provider, token) and isinstance(token, _PublicAgentAccessToken):
        return token.identity
    return None


def is_agent_access_token(provider: object, token: object) -> bool:
    return _qualified_source(provider, token) == _AGENT_SOURCE


def effective_oauth_provider(provider: object, token: object) -> object:
    if type(provider) is PublicAgentMultiAuth:
        return provider.server if _qualified_source(provider, token) == _OAUTH_SOURCE else None
    if isinstance(token, _PublicAgentAccessToken):
        return None
    return provider
