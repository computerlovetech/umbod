"""Deployment ports; OAuth decisions and state transitions stay in the service."""

from dataclasses import dataclass
from typing import Literal, Protocol
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
