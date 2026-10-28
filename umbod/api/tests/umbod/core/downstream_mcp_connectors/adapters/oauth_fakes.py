from types import TracebackType
from typing import Self

from mcp.client.auth import AuthorizationCodeResult
from mcp.shared.auth import OAuthToken

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    ConnectorOAuthStorage,
)
from umbod.core.connectors.downstream_mcp.oauth.ports import (
    AuthorizationBeginOptions,
    CallbackHandler,
    OAuthDiscoveryPreview,
    RedirectHandler,
)


class ScriptedSession:
    def __init__(
        self,
        storage: ConnectorOAuthStorage,
        failure: str,
        redirect_handler: RedirectHandler,
        callback_handler: CallbackHandler,
        interactive: bool,
    ) -> None:
        self.storage = storage
        self.failure = failure
        self.redirect_handler = redirect_handler
        self.callback_handler = callback_handler
        self.interactive = interactive
        self.token_received = False
        self.disposed = False

    async def __aenter__(self) -> Self:
        try:
            if self.interactive:
                await self.redirect_handler(
                    "https://auth.example/authorize?state=expected"
                )
                await self.callback_handler()
            if self.failure == "authorization":
                raise ValueError("access_token=secret")
            await self.storage.set_tokens(
                OAuthToken(access_token="secret", token_type="Bearer", scope="read")
            )
            self.token_received = True
            if self.failure == "enter_after_tokens":
                raise ValueError("access_token=secret")
            return self
        except BaseException:
            self.disposed = True
            raise

    async def discover_tools(self) -> None:
        if self.failure == "discovery":
            raise ValueError("access_token=secret")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.disposed = True


class ScriptedSessionFactory:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.sessions: list[ScriptedSession] = []
        self.options: list[AuthorizationBeginOptions] = []

    def begin(
        self,
        storage: ConnectorOAuthStorage,
        options: AuthorizationBeginOptions,
        redirect_handler: RedirectHandler,
        callback_handler: CallbackHandler,
    ) -> ScriptedSession:
        self.options.append(options)
        session = ScriptedSession(
            storage, self.failure, redirect_handler, callback_handler, True
        )
        self.sessions.append(session)
        return session

    def refresh(self, storage: ConnectorOAuthStorage) -> ScriptedSession:
        async def redirect_handler(url: str) -> None:
            raise AssertionError("Refresh cannot redirect")

        async def callback_handler() -> AuthorizationCodeResult:
            raise AssertionError("Refresh cannot request a callback")

        session = ScriptedSession(
            storage, self.failure, redirect_handler, callback_handler, False
        )
        self.sessions.append(session)
        return session


class MemoryDiscovery:
    def __init__(self) -> None:
        self.endpoints: list[str] = []
        self.preview = OAuthDiscoveryPreview(
            canonical_endpoint="https://tools.example/mcp",
            endpoint_differs=False,
            issuer="https://auth.example",
            available_scopes=["read"],
            registration="hosted_metadata",
        )

    async def discover(self, endpoint: str) -> OAuthDiscoveryPreview:
        self.endpoints.append(endpoint)
        return self.preview
