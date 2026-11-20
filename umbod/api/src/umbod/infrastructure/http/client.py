from collections.abc import Mapping

import anyio
import httpx
from pydantic import BaseModel, ConfigDict, PositiveFloat, PositiveInt


class HttpRequestError(RuntimeError):
    pass


class OutboundHttpClientFactory:
    def __init__(
        self,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        write_timeout_seconds: float,
        pool_timeout_seconds: float,
    ) -> None:
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=write_timeout_seconds,
            pool=pool_timeout_seconds,
        )

    def create(self) -> httpx.AsyncClient:
        return self._create("")

    def create_for_origin(self, base_url: str) -> httpx.AsyncClient:
        return self._create(base_url)

    def _create(self, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            trust_env=False,
            follow_redirects=False,
            timeout=self._timeout,
        )


class JsonHttpLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    timeout_seconds: PositiveFloat = 10.0
    maximum_response_bytes: PositiveInt = 4_000_000


class AsyncJsonHttpClient:
    def __init__(self, client: httpx.AsyncClient, *, limits: JsonHttpLimits) -> None:
        if not client.base_url.is_absolute_url or client.base_url.scheme not in {
            "http",
            "https",
        }:
            raise ValueError("An HTTP base URL is required")
        self._client = client
        self._limits = limits

    async def get_json(self, path: str, *, params: Mapping[str, str | int]) -> bytes:
        if (
            not path.startswith("/")
            or path.startswith("//")
            or any(character in path for character in "\\?#")
            or any(character.isspace() or ord(character) < 32 for character in path)
        ):
            raise ValueError("An origin-relative HTTP path is required")
        url = self._client.base_url.join(path)
        request = httpx.Request(
            "GET",
            url,
            params=params,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )
        try:
            with anyio.fail_after(self._limits.timeout_seconds):
                response = await self._client.send(
                    request, auth=None, follow_redirects=False, stream=True
                )
                try:
                    response.raise_for_status()
                    if (
                        response.headers.get("Content-Encoding", "identity").lower()
                        != "identity"
                    ):
                        raise HttpRequestError(
                            "HTTP response uses unsupported content encoding"
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > self._limits.maximum_response_bytes:
                            raise HttpRequestError(
                                "HTTP response exceeds the size limit"
                            )
                        body.extend(chunk)
                    return bytes(body)
                finally:
                    await response.aclose()
        except httpx.HTTPError, TimeoutError:
            raise HttpRequestError("HTTP request failed") from None
