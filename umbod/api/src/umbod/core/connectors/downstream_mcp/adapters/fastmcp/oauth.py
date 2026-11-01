"""MCP SDK OAuth adapter. One encrypted authorization belongs to one connector.

Interactive callbacks are supplied by the hosting product, never by tool calls.
SDK-specific token and issuer metadata stay out of the connector domain model.
"""

import asyncio
from typing import TypedDict, Unpack
from weakref import WeakValueDictionary
from collections.abc import Awaitable, Callable

from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientMetadata,
)
import httpx2

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage import ConnectorOAuthStorage


class SignInRequired(ValueError):
    def __init__(self) -> None:
        super().__init__("This connection needs browser sign-in. Open Umbod to reconnect it.")


_authorization_locks: WeakValueDictionary = WeakValueDictionary()


async def require_sign_in(_url: str) -> None:
    raise SignInRequired()


class ConnectorOAuthOptions(TypedDict, total=False):
    redirect_uri: str
    redirect_handler: Callable[[str], Awaitable[None]]
    callback_handler: Callable[[], Awaitable[AuthorizationCodeResult]] | None


class ConnectorOAuth(OAuthClientProvider):
    def __init__(
        self,
        storage: ConnectorOAuthStorage,
        **options: Unpack[ConnectorOAuthOptions],
    ) -> None:
        unknown_options = options.keys() - ConnectorOAuthOptions.__annotations__.keys()
        if unknown_options:
            raise TypeError(f"Unexpected OAuth options: {sorted(unknown_options)}")
        self.storage = storage
        redirect_uri = options.get("redirect_uri", "http://127.0.0.1/oauth/callback")
        redirect_handler = options.get("redirect_handler", require_sign_in)
        callback_handler = options.get("callback_handler")
        super().__init__(
            server_url=storage.document.endpoint_url,
            client_metadata=OAuthClientMetadata(
                client_name="Umbod",
                redirect_uris=[redirect_uri],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
            ),
            storage=storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )

    async def _initialize(self) -> None:
        await self.storage.load()
        await super()._initialize()
        self.context.token_expiry_time = self.storage.document.expires_at
        self.context.oauth_metadata = self.storage.document.metadata
        self.context.auth_server_url = self.storage.document.authorization_server

    async def _handle_oauth_metadata_response(self, response: httpx2.Response) -> None:
        await super()._handle_oauth_metadata_response(response)
        self.storage.document.metadata = self.context.oauth_metadata
        self.storage.document.authorization_server = self.context.auth_server_url
        await self.storage.save()

    async def _perform_authorization(self) -> httpx2.Request:
        # Fail before registration/browser interaction in background runtime clients.
        if self.context.callback_handler is None:
            raise SignInRequired()
        return await super()._perform_authorization()

    async def async_auth_flow(self, request: httpx2.Request):
        # Local's API and MCP clients share a process, but not provider instances.
        # Serialize token use/rotation and reload the latest encrypted document.
        key = (
            id(asyncio.get_running_loop()),
            self.storage.connector_id or id(self.storage),
            self.storage.document.endpoint_url,
        )
        lock = _authorization_locks.setdefault(key, asyncio.Lock())
        async with lock:
            self._initialized = False
            flow = super().async_auth_flow(request)
            response = None
            try:
                while True:
                    try:
                        outgoing = await flow.asend(response)
                    except StopAsyncIteration:
                        return
                    metadata = self.context.oauth_metadata
                    if (
                        self.context.callback_handler is None
                        and metadata is not None
                        and metadata.registration_endpoint is not None
                        and str(outgoing.url) == str(metadata.registration_endpoint)
                    ):
                        raise SignInRequired()
                    response = yield outgoing
            finally:
                await flow.aclose()
