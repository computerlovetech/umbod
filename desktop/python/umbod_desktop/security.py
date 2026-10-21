"""Single-user authentication and OS-vault credentials; no development fallback."""

import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .contracts import DESKTOP_GROUP as DESKTOP_GROUP
from .ports import CredentialVault as CredentialVault


class KeychainVault:
    def __init__(self, profile: str, namespace: str = "") -> None:
        from keyring.backends.macOS import Keyring

        self.backend = Keyring()
        self.service = (
            "app.umbod.desktop" + (".dev" if profile == "dev" else "") + namespace
        )

    def get(self, reference: str) -> str | None:
        return self.backend.get_password(self.service, reference)

    def set(self, reference: str, value: str) -> None:
        self.backend.set_password(self.service, reference, value)

    def delete(self, reference: str) -> None:
        if self.get(reference) is not None:
            self.backend.delete_password(self.service, reference)


def persistent_secret(vault: CredentialVault, reference: str) -> str:
    value = vault.get(reference)
    if value is None:
        value = secrets.token_urlsafe(48)
        vault.set(reference, value)
    if len(value) < 32:
        raise ValueError("Stored desktop credential is invalid")
    return value


class LoopbackAuthentication:
    """Protect every host route, including health and internal system routes."""

    def __init__(
        self, app: ASGIApp, token: str, forward_authorization: bool = True
    ) -> None:
        self.app, self.token = app, token
        self.forward_authorization = forward_authorization

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"authorization", b"")
        # Browser origins/cookies have no place in this native-only host contract.
        if (
            b"origin" in headers
            or b"cookie" in headers
            or not secrets.compare_digest(supplied, f"Bearer {self.token}".encode())
        ):
            await JSONResponse({"detail": "Unauthorized"}, status_code=401)(
                scope, receive, send
            )
            return
        if not self.forward_authorization:
            scope = {
                **scope,
                "headers": [
                    (name, value)
                    for name, value in scope.get("headers", [])
                    if name.lower() != b"authorization"
                ],
            }
        await self.app(scope, receive, send)
