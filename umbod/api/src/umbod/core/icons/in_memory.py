from collections.abc import Mapping

from .models import FaviconDiscoveryRequest, FaviconFound, FaviconNotFound


class InMemoryFaviconDiscoveryStrategy:
    def __init__(self, results: Mapping[str, FaviconFound | FaviconNotFound]) -> None:
        self._results = dict(results)

    async def discover(
        self, request: FaviconDiscoveryRequest
    ) -> FaviconFound | FaviconNotFound:
        return self._results.get(str(request.endpoint_url), FaviconNotFound())
