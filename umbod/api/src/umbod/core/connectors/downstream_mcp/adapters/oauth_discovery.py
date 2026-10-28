from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import httpx2

from umbod.core.connectors.downstream_mcp.oauth.discovery import discover
from umbod.core.connectors.downstream_mcp.oauth.ports import OAuthDiscoveryPreview


class HttpOAuthDiscovery:
    def __init__(
        self, clients: Callable[[], AbstractAsyncContextManager[httpx2.AsyncClient]]
    ) -> None:
        self.clients = clients

    async def discover(self, endpoint: str) -> OAuthDiscoveryPreview:
        async with self.clients() as client:
            return OAuthDiscoveryPreview.model_validate(
                await discover(endpoint, client)
            )
