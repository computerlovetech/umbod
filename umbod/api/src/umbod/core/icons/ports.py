from typing import Protocol

from .models import (
    FaviconDiscoveryRequest,
    FaviconDiscoveryResult,
    FaviconFound,
    FaviconNotFound,
)


class FaviconDiscoveryStrategy(Protocol):
    async def discover(
        self, request: FaviconDiscoveryRequest
    ) -> FaviconFound | FaviconNotFound: ...


class FaviconDiscovery(Protocol):
    async def discover(
        self, request: FaviconDiscoveryRequest
    ) -> FaviconDiscoveryResult: ...
