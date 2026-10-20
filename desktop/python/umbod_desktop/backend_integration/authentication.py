import secrets
from collections.abc import Callable

from umbod.hosting import AccessToken, JwtClaims, JwtVerificationError, TokenVerifier

from ..contracts import DESKTOP_GROUP


class DesktopAdminVerifier:
    def __init__(self, token: str) -> None:
        self.token = token

    def verify(self, token: str) -> JwtClaims:
        if not secrets.compare_digest(token.encode(), self.token.encode()):
            raise JwtVerificationError("Invalid desktop credential")
        return JwtClaims(
            claims={"sub": "desktop-owner", "name": "You", "groups": [DESKTOP_GROUP]}
        )


def reject_additional_credential(token: str) -> bool:
    return False


class DesktopAgentVerifier(TokenVerifier):
    def __init__(
        self, token: str,
        additional_credential: Callable[[str], bool] = reject_additional_credential,
    ) -> None:
        super().__init__()
        self.token = token
        self.additional_credential = additional_credential

    async def verify_token(self, token: str) -> AccessToken | None:
        if not secrets.compare_digest(token.encode(), self.token.encode()) and not self.additional_credential(token):
            return None
        return AccessToken(
            token=token,
            client_id="desktop-agent",
            scopes=[],
            subject="desktop-owner",
            claims={"sub": "desktop-owner", "groups": [DESKTOP_GROUP]},
        )


