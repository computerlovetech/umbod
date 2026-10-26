from typing import Protocol

from .http_models import FaviconHttpRequest, FaviconHttpResult


class FaviconHttpClient(Protocol):
    async def fetch(self, request: FaviconHttpRequest) -> FaviconHttpResult: ...
