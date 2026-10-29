from collections.abc import Mapping

from umbod.core.icons.http_models import FaviconHttpRequest, FaviconHttpResult, FaviconHttpUnavailable
from umbod.core.icons.models import FaviconDiscoveryRequest, FaviconFound, FaviconNotFound


class InMemoryFaviconHttpClient:
    def __init__(self, responses: dict[str, FaviconHttpResult]) -> None:
        self._responses = dict(responses)
        self.requests: list[FaviconHttpRequest] = []

    async def fetch(self, request: FaviconHttpRequest) -> FaviconHttpResult:
        self.requests.append(request)
        return self._responses.get(str(request.url), FaviconHttpUnavailable())


class InMemoryFaviconDiscoveryStrategy:
    def __init__(self, results: Mapping[str, FaviconFound | FaviconNotFound]) -> None:
        self._results = dict(results)

    async def discover(
        self, request: FaviconDiscoveryRequest
    ) -> FaviconFound | FaviconNotFound:
        return self._results.get(str(request.endpoint_url), FaviconNotFound())
