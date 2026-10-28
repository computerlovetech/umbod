from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Protocol, Self

from fastmcp import Client

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    ConnectorOAuthStorage,
)
from umbod.core.connectors.downstream_mcp.oauth.ports import (
    AuthorizationBeginOptions,
    CallbackHandler,
    RedirectHandler,
)
from umbod.core.connectors.downstream_mcp.oauth.provider import (
    CLIENT_METADATA_URL,
    InteractiveConnectorOAuth,
)


class OAuthClientFactory(Protocol):
    def __call__(
        self, endpoint_url: str, auth: InteractiveConnectorOAuth
    ) -> AbstractAsyncContextManager[Client]: ...


class FastMCPOAuthSession:
    def __init__(
        self,
        authorization: InteractiveConnectorOAuth,
        client: AbstractAsyncContextManager[Client],
    ) -> None:
        self.authorization = authorization
        self.client_context = client

    @property
    def token_received(self) -> bool:
        return self.authorization.token_received

    async def __aenter__(self) -> Self:
        self.client = await self.client_context.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return await self.client_context.__aexit__(exc_type, exc, traceback)

    async def discover_tools(self) -> None:
        await self.client.list_tools()


class FastMCPOAuthSessionFactory:
    def __init__(self, clients: OAuthClientFactory) -> None:
        self.clients = clients

    def begin(
        self,
        storage: ConnectorOAuthStorage,
        options: AuthorizationBeginOptions,
        redirect_handler: RedirectHandler,
        callback_handler: CallbackHandler,
    ) -> FastMCPOAuthSession:
        authorization = InteractiveConnectorOAuth(
            storage,
            requested_scope=options.requested_scopes,
            metadata_url=CLIENT_METADATA_URL
            if options.metadata_mode == "hosted_metadata"
            else None,
            force_authorization=True,
            redirect_uri=options.redirect_uri,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )
        return FastMCPOAuthSession(
            authorization, self.clients(str(options.endpoint), authorization)
        )

    def refresh(self, storage: ConnectorOAuthStorage) -> FastMCPOAuthSession:
        authorization = InteractiveConnectorOAuth(storage, force_refresh=True)
        return FastMCPOAuthSession(
            authorization, self.clients(storage.document.endpoint_url, authorization)
        )
