import gzip

import httpx
import pytest

from umbod.infrastructure.http import (
    AsyncJsonHttpClient,
    HttpRequestError,
    JsonHttpLimits,
    OutboundHttpClientFactory,
)


@pytest.mark.asyncio
async def test_factory_preserves_hardened_outbound_client_configuration() -> None:
    factory = OutboundHttpClientFactory(1.0, 2.0, 3.0, 4.0)
    async with factory.create() as client:
        assert client.trust_env is False
        assert client.follow_redirects is False
        assert client.timeout == httpx.Timeout(
            connect=1.0, read=2.0, write=3.0, pool=4.0
        )


@pytest.mark.asyncio
async def test_json_reader_does_not_forward_client_credentials() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        assert "Cookie" not in request.headers
        return httpx.Response(200, content=b"{}")

    async with httpx.AsyncClient(
        base_url="https://api.example.test",
        auth=("user", "token"),
        cookies={"session": "secret"},
        transport=httpx.MockTransport(respond),
    ) as client:
        response = await AsyncJsonHttpClient(client, limits=JsonHttpLimits()).get_json(
            "/servers", params={}
        )

    assert response == b"{}"


@pytest.mark.asyncio
async def test_json_reader_does_not_follow_redirects() -> None:
    hits: list[str] = []

    async def redirect(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        return httpx.Response(302, headers={"Location": "https://other.example.test"})

    async with httpx.AsyncClient(
        base_url="https://api.example.test",
        follow_redirects=True,
        transport=httpx.MockTransport(redirect),
    ) as client:
        with pytest.raises(HttpRequestError):
            await AsyncJsonHttpClient(client, limits=JsonHttpLimits()).get_json(
                "/servers", params={}
            )

    assert hits == ["api.example.test"]


@pytest.mark.asyncio
async def test_json_reader_rejects_unrequested_compression() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(
            200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(b"{}")
        )

    async with httpx.AsyncClient(
        base_url="https://api.example.test", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(HttpRequestError, match="content encoding"):
            await AsyncJsonHttpClient(client, limits=JsonHttpLimits()).get_json(
                "/servers", params={}
            )


@pytest.mark.asyncio
async def test_json_reader_rejects_responses_larger_than_its_limit() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{}")

    async with httpx.AsyncClient(
        base_url="https://api.example.test", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(HttpRequestError, match="size limit"):
            await AsyncJsonHttpClient(
                client, limits=JsonHttpLimits(maximum_response_bytes=1)
            ).get_json("/servers", params={})
