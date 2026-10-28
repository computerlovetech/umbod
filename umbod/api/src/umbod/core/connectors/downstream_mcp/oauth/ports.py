"""Deployment ports; OAuth decisions and state transitions stay in the service."""

from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Literal, Protocol, Self

from mcp.client.auth import AuthorizationCodeResult
from pydantic import BaseModel

from umbod.core.connectors.downstream_mcp.models import EndpointUrl
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    ConnectorOAuthStorage,
)


@dataclass(frozen=True)
class OAuthConnection:
    endpoint_url: str
    requested_scopes: str = ""
    authorization_mode: Literal["shared", "personal"] = "shared"


@dataclass(frozen=True)
class CallbackResult:
    content: str
    status_code: int = 200


RedirectHandler = Callable[[str], Awaitable[None]]
CallbackHandler = Callable[[], Awaitable[AuthorizationCodeResult]]


class AuthorizationBeginOptions(BaseModel):
    endpoint: EndpointUrl
    requested_scopes: str
    metadata_mode: Literal["hosted_metadata", "registration"]
    redirect_uri: str


class OAuthDiscoveryPreview(BaseModel):
    canonical_endpoint: EndpointUrl
    endpoint_differs: bool
    issuer: str
    available_scopes: list[str]
    registration: Literal["unknown", "hosted_metadata", "automatic", "manual"]


class AuthorizationSession(Protocol):
    @property
    def token_received(self) -> bool: ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...
    async def discover_tools(self) -> None: ...


class AuthorizationSessionFactory(Protocol):
    def begin(
        self,
        storage: ConnectorOAuthStorage,
        options: AuthorizationBeginOptions,
        redirect_handler: RedirectHandler,
        callback_handler: CallbackHandler,
    ) -> AuthorizationSession: ...

    def refresh(self, storage: ConnectorOAuthStorage) -> AuthorizationSession: ...


class OAuthDiscovery(Protocol):
    async def discover(self, endpoint: str) -> OAuthDiscoveryPreview: ...


class OAuthHost(Protocol):
    statuses: dict[str, str]

    def resolve(self, connector_id: str) -> str: ...
    def connection(self, key: str) -> OAuthConnection: ...
    def storage(self, key: str) -> ConnectorOAuthStorage: ...
    def callback_url(self, key: str, *, shared: bool) -> str: ...
    def set_scopes(self, key: str, scopes: str) -> None: ...
    def set_authorized(self, key: str, authorized: bool) -> None: ...
    async def delete_authorization(self, key: str) -> None: ...
    async def reconnect(self, key: str) -> None: ...
