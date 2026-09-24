from typing import Protocol

from fastmcp.server.auth.auth import AccessToken, TokenVerifier as FastMCPTokenVerifier


class TokenValidator(Protocol):
    def validate_user(self, token: str) -> str | None:
        raise NotImplementedError


class FakeTokenValidator:
    def __init__(self, valid_tokens: dict[str, str]) -> None:
        self._valid_tokens = valid_tokens

    def validate_user(self, token: str) -> str | None:
        return self._valid_tokens.get(token)


class TokenValidatorAuthProvider(FastMCPTokenVerifier):
    def __init__(self, token_validator: TokenValidator, base_url: str) -> None:
        super().__init__(base_url=base_url)
        self._token_validator = token_validator

    async def verify_token(self, token: str) -> AccessToken | None:
        email = self._token_validator.validate_user(token)
        if email is None:
            return None
        return AccessToken(
            token=token,
            client_id=email,
            scopes=[],
            claims={"email": email},
        )
