from typing import cast

import jwt
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
from mcp.server.auth.provider import AuthorizationCode, RefreshToken
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import Field
from umbod.mcp.proxies import Model


class AuthenticatedUser(Model):
    email: str = Field(min_length=1)


def _build_access_token_from_jwt(token: str) -> AccessToken:
    claims = cast(dict[str, object], jwt.decode(token, options={"verify_signature": False}))
    email = claims.get("email")
    user = AuthenticatedUser(email=email) if isinstance(email, str) else None
    if user is None:
        raise ValueError("Test user JWT must include an email claim")
    return AccessToken(
        token=token,
        client_id=user.email,
        scopes=[],
        claims=claims,
    )


def _copy_claims_to_access_token(
    access_token: AccessToken, claims: dict[str, object]
) -> AccessToken:
    return AccessToken(
        token=access_token.token,
        client_id=access_token.client_id,
        scopes=access_token.scopes,
        expires_at=access_token.expires_at,
        resource=access_token.resource,
        claims=dict(claims),
    )


class SingleTestUserOAuthProvider(InMemoryOAuthProvider):
    def __init__(
        self,
        bearer_token: str,
        base_url: str,
    ) -> None:
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self._test_user_access_token = _build_access_token_from_jwt(bearer_token)
        self._test_user_claims = dict(self._test_user_access_token.claims or {})
        self.access_tokens[bearer_token] = self._test_user_access_token

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        oauth_token = await super().exchange_authorization_code(client, authorization_code)
        self._apply_test_user_claims(oauth_token.access_token)
        return oauth_token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        oauth_token = await super().exchange_refresh_token(client, refresh_token, scopes)
        self._apply_test_user_claims(oauth_token.access_token)
        return oauth_token

    def _apply_test_user_claims(self, access_token_value: str) -> None:
        access_token = self.access_tokens.get(access_token_value)
        if access_token is not None:
            self.access_tokens[access_token_value] = _copy_claims_to_access_token(
                access_token, self._test_user_claims
            )
