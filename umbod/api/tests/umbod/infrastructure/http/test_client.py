import asyncio
import gzip
import ssl
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import replace

import httpx
import pytest
from pydantic import ValidationError

from umbod.core.network.http import (
    ClientHttpTimeout,
    HttpRedirectPolicy,
    HttpRequest,
    HttpTimeoutError,
    HttpTlsError,
    HttpTransportError,
    JsonHttpBody,
    NoHttpBody,
)
from umbod.infrastructure.http import (
    AsyncJsonHttpClient,
    HttpRequestError,
    JsonHttpLimits,
    OutboundHttpClientFactory,
    OutboundHttpClientOptions,
)
from umbod.infrastructure.http.httpx_client import HttpxClientProxy


@pytest.mark.asyncio
async def test_factory_preserves_hardened_outbound_client_configuration() -> None:
    factory = OutboundHttpClientFactory.hardened(1.0, 2.0, 3.0, 4.0)
    async with aclosing(factory.create()) as client:
        assert isinstance(client, HttpxClientProxy)
        assert not isinstance(client, httpx.AsyncClient)
        assert client._client.trust_env is False
        assert client._client.follow_redirects is False
        assert client._client.timeout == httpx.Timeout(
            connect=1.0, read=2.0, write=3.0, pool=4.0
        )
    assert client._client.is_closed


@pytest.mark.asyncio
async def test_factory_applies_explicit_options_to_origin_bound_client() -> None:
    options = OutboundHttpClientOptions(
        use_environment_settings=True,
        follow_redirects=True,
        max_connections=8,
        max_idle_connections=2,
        idle_connection_timeout_seconds=30.0,
    )
    factory = OutboundHttpClientFactory(1.0, 2.0, 3.0, 4.0, options=options)

    async with aclosing(factory.create_for_origin("https://api.example.test/")) as client:
        assert isinstance(client, HttpxClientProxy)
        assert client.base_url == "https://api.example.test/"
        assert client._client.trust_env is True
        assert client._client.follow_redirects is True


def test_client_options_reject_idle_pool_larger_than_total_pool() -> None:
    with pytest.raises(ValidationError, match="Maximum idle connections"):
        OutboundHttpClientOptions(
            use_environment_settings=False,
            follow_redirects=False,
            max_connections=2,
            max_idle_connections=3,
            idle_connection_timeout_seconds=5.0,
        )


@pytest.mark.asyncio
async def test_proxy_maps_requests_and_responses_without_exposing_httpx() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://api.example.test/items?limit=1"
        assert request.headers["Authorization"] == "Bearer explicit-token"
        assert request.headers["Content-Type"] == "application/json"
        assert request.content == b'{"name":"item"}'
        assert request.extensions["timeout"]["read"] == 2.5
        return httpx.Response(201, headers={"ETag": "revision"}, content=b"created")

    raw_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    async with aclosing(HttpxClientProxy(raw_client)) as client:
        request = HttpRequest(
            method="POST",
            url="https://api.example.test/items?limit=1",
            headers={"Authorization": "Bearer explicit-token"},
            query={},
            body=JsonHttpBody({"name": "item"}),
            timeout=2.5,
            redirects=HttpRedirectPolicy.DENY,
        )
        async with client.stream(request) as response:
            assert not isinstance(response, httpx.Response)
            assert response.status_code == 201
            assert response.headers["etag"] == "revision"
            assert b"".join([chunk async for chunk in response.aiter_bytes()]) == b"created"
    assert raw_client.is_closed


@pytest.mark.asyncio
async def test_proxy_distinguishes_explicit_json_null_from_no_body() -> None:
    payloads: list[tuple[bytes, str]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        payloads.append((request.content, request.headers.get("content-type", "")))
        return httpx.Response(204)

    async with aclosing(HttpxClientProxy(httpx.AsyncClient(transport=httpx.MockTransport(respond)))) as client:
        request = replace(_get_request(), method="POST")
        for body in (NoHttpBody(), JsonHttpBody(None)):
            async with client.stream(replace(request, body=body)) as response:
                assert response.status_code == 204

    assert payloads == [(b"", ""), (b"null", "application/json")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_error,expected_error",
    [
        (httpx.ConnectTimeout("private timeout"), HttpTimeoutError),
        (httpx.ConnectError("private connection failure"), HttpTransportError),
        (httpx.ProtocolError("private protocol failure"), HttpTransportError),
    ],
)
async def test_proxy_maps_request_errors_to_neutral_exceptions(
    source_error: httpx.HTTPError, expected_error: type[HttpTransportError],
) -> None:
    async def fail(request: httpx.Request) -> httpx.Response:
        raise source_error

    async with aclosing(HttpxClientProxy(httpx.AsyncClient(transport=httpx.MockTransport(fail)))) as client:
        with pytest.raises(expected_error) as caught:
            async with client.stream(_get_request()):
                pytest.fail("failed response was yielded")
    assert type(caught.value) is expected_error
    assert "private" not in str(caught.value)


@pytest.mark.asyncio
async def test_proxy_distinguishes_tls_from_other_connection_errors() -> None:
    async def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private connection failure") from ssl.SSLError("private TLS failure")

    async with aclosing(HttpxClientProxy(httpx.AsyncClient(transport=httpx.MockTransport(fail)))) as client:
        with pytest.raises(HttpTlsError, match="HTTP TLS connection failed"):
            async with client.stream(_get_request()):
                pytest.fail("failed response was yielded")


@pytest.mark.asyncio
async def test_proxy_translates_stream_read_timeout_and_closes_response() -> None:
    class TimedOutStream(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"first"
            raise httpx.ReadTimeout("private timeout")

        async def aclose(self) -> None:
            self.closed = True

    stream = TimedOutStream()

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    async with aclosing(HttpxClientProxy(httpx.AsyncClient(transport=httpx.MockTransport(respond)))) as client:
        async with client.stream(_get_request()) as response:
            assert await anext(response.aiter_bytes()) == b"first"
            with pytest.raises(HttpTimeoutError):
                await anext(response.aiter_bytes())

    assert stream.closed


@pytest.mark.asyncio
async def test_proxy_only_follows_same_origin_without_ambient_cookies() -> None:
    hits: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        assert "Cookie" not in request.headers
        assert request.headers["X-Api-Key"] == "explicit-secret"
        if request.url.path == "/items":
            return httpx.Response(302, headers={"Location": "/next", "Set-Cookie": "session=ambient"})
        return httpx.Response(302, headers={"Location": "https://other.example.test/"})

    raw_client = httpx.AsyncClient(follow_redirects=True, transport=httpx.MockTransport(respond))
    async with aclosing(HttpxClientProxy(raw_client)) as client:
        request = replace(
            _get_request(), headers={"X-Api-Key": "explicit-secret"},
            redirects=HttpRedirectPolicy.CLIENT_DEFAULT,
        )
        async with client.stream(request) as response:
            assert response.status_code == 302
            assert response.headers["location"] == "https://other.example.test/"

    assert hits == ["https://api.example.test/items", "https://api.example.test/next"]


@pytest.mark.asyncio
async def test_proxy_completes_client_teardown_when_cancelled() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    closed = asyncio.Event()

    class PausedTransport(httpx.AsyncBaseTransport):
        async def aclose(self) -> None:
            entered.set()
            await release.wait()
            closed.set()

    client = HttpxClientProxy(httpx.AsyncClient(transport=PausedTransport()))
    close = asyncio.create_task(client.aclose())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        close.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(close, timeout=2)
    assert closed.is_set()


def _get_request() -> HttpRequest:
    return HttpRequest(
        method="GET",
        url="https://api.example.test/items",
        headers={},
        query={},
        body=NoHttpBody(),
        timeout=ClientHttpTimeout.DEFAULT,
        redirects=HttpRedirectPolicy.DENY,
    )


@pytest.mark.asyncio
async def test_json_reader_does_not_forward_client_credentials() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        assert "Cookie" not in request.headers
        assert "X-Api-Key" not in request.headers
        return httpx.Response(200, content=b"{}")

    async with httpx.AsyncClient(
        base_url="https://api.example.test",
        auth=("user", "token"),
        cookies={"session": "secret"},
        headers={"X-Api-Key": "inherited-secret"},
        transport=httpx.MockTransport(respond),
    ) as client:
        response = await AsyncJsonHttpClient(
            HttpxClientProxy(client), limits=JsonHttpLimits(),
        ).get_json("/servers", params={})

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
            await AsyncJsonHttpClient(
                HttpxClientProxy(client), limits=JsonHttpLimits(),
            ).get_json("/servers", params={})

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
            await AsyncJsonHttpClient(
                HttpxClientProxy(client), limits=JsonHttpLimits(),
            ).get_json("/servers", params={})


@pytest.mark.asyncio
async def test_json_reader_rejects_responses_larger_than_its_limit() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{}")

    async with httpx.AsyncClient(
        base_url="https://api.example.test", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(HttpRequestError, match="size limit"):
            await AsyncJsonHttpClient(
                HttpxClientProxy(client), limits=JsonHttpLimits(maximum_response_bytes=1)
            ).get_json("/servers", params={})
