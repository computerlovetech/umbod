from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import PlainTextResponse
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    AuthorizationDocument,
    ConnectorOAuthStorage,
    SignInRequired,
)
from umbod.core.connectors.downstream_mcp.oauth.ports import OAuthConnection
from umbod.hosting import OAuthService

from ..ports import CredentialVault

if TYPE_CHECKING:
    from .transports import DesktopUpstreams


class KeychainOAuthStorage(ConnectorOAuthStorage):
    def __init__(self, vault: CredentialVault, key: str, url: str) -> None:
        super().__init__(AuthorizationDocument(endpoint_url=url), connector_id=key)
        self.vault, self.reference = vault, f"python:oauth:{key}"
        self.expected_value = None

    async def load(self) -> None:
        value = self.vault.get(self.reference)
        self.expected_value = value
        self.document = AuthorizationDocument(endpoint_url=self.document.endpoint_url)
        if value:
            document = AuthorizationDocument.model_validate_json(value)
            if document.endpoint_url != self.document.endpoint_url:
                raise ValueError("OAuth endpoint changed; sign in again")
            self.document = document

    async def save(self) -> None:
        if self.vault.get(self.reference) != self.expected_value:
            raise SignInRequired()
        value = self.document.model_dump_json()
        self.vault.set(self.reference, value)
        self.expected_value = value


class DesktopOAuthHost:
    def __init__(self, upstreams: "DesktopUpstreams") -> None:
        self.upstreams = upstreams
        self.statuses = getattr(upstreams, "authentication_status", {})

    def resolve(self, connector_id: str) -> str:
        servers = self.upstreams.state.data["servers"]
        if connector_id.startswith("pending:"):
            key = connector_id.removeprefix("pending:")
            if key in servers:
                return key
        for key, server in servers.items():
            if server.get("id") == connector_id:
                return key
        raise KeyError(connector_id)

    def connection(self, key: str) -> OAuthConnection:
        server = self.upstreams.state.data["servers"][key]
        if server.get("transport", "http") != "http":
            raise ValueError("Browser sign-in requires an HTTPS connector")
        return OAuthConnection(server["url"], server.get("oauth_scopes", ""))

    def storage(self, key: str) -> KeychainOAuthStorage:
        return KeychainOAuthStorage(self.upstreams.vault, key, self.connection(key).endpoint_url)

    def callback_url(self, key: str, *, shared: bool) -> str:
        return f"{self.upstreams.origin}/desktop/oauth/callback" + ("" if shared else f"/{key}")

    def set_scopes(self, key: str, scopes: str) -> None:
        self.upstreams.state.data["servers"][key]["oauth_scopes"] = scopes
        self.upstreams.state.save()

    def set_authorized(self, key: str, authorized: bool) -> None:
        self.upstreams.state.data["servers"][key]["oauth"] = authorized
        self.upstreams.state.save()

    async def delete_authorization(self, key: str) -> None:
        self.upstreams.vault.delete(f"python:oauth:{key}")

    async def reconnect(self, key: str) -> None:
        await self.upstreams.start(key, self.upstreams.state.data["servers"][key])


def callback_transport(oauth: OAuthService) -> Callable[[Request], Awaitable[PlainTextResponse]]:
    async def callback(request: Request) -> PlainTextResponse:
        result = await oauth.callback(request.path_params.get("nonce"), dict(request.query_params))
        return PlainTextResponse(result.content, status_code=result.status_code)
    return callback

