from ..http_models import FaviconHttpRequest, FaviconHttpResult, FaviconHttpUnavailable


class InMemoryFaviconHttpClient:
    def __init__(self, responses: dict[str, FaviconHttpResult]) -> None:
        self._responses = dict(responses)
        self.requests: list[FaviconHttpRequest] = []

    async def fetch(self, request: FaviconHttpRequest) -> FaviconHttpResult:
        self.requests.append(request)
        return self._responses.get(str(request.url), FaviconHttpUnavailable())
