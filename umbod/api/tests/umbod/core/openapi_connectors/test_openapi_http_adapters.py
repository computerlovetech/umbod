import ssl
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import AsyncIterator
from unittest.mock import Mock, patch

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from umbod.core.connectors.openapi.execution import (
    AuthenticatedOutboundRequest,
    ExactHttpsDestinationPolicy,
    HttpxOutboundOperationAdapter,
    HttpxSpecificationFetcher,
    OutboundHttpClientFactory,
    OutboundNetworkError,
    OutboundPolicyError,
    OutboundRedirectError,
    OutboundRequest,
    OutboundTimeoutError,
    OutboundTlsError,
    OutboundTransportError,
    SpecificationFetchRequest,
    TrustedBearerAuthorization,
)


class FakeStreamResponse:
    def __init__(self, status: int, headers: dict[str, str], chunks: tuple[bytes, ...]) -> None:
        self.status_code = status
        self.headers = httpx.Headers(headers)
        self._chunks = chunks

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@asynccontextmanager
async def _response_context(
    response: FakeStreamResponse,
) -> AsyncIterator[FakeStreamResponse]:
    yield response


class RaisingAsyncHttpClient:
    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.calls = 0

    def stream(
        self, method: str, url: str, **kwargs: object
    ) -> AbstractAsyncContextManager[FakeStreamResponse]:
        self.calls += 1

        @asynccontextmanager
        async def raising_context() -> AsyncIterator[FakeStreamResponse]:
            raise self._error
            yield FakeStreamResponse(200, {}, ())

        return raising_context()


class RecordingAsyncHttpClient:
    def __init__(self, response: FakeStreamResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def stream(
        self, method: str, url: str, **kwargs: object
    ) -> AbstractAsyncContextManager[FakeStreamResponse]:
        self.calls.append((method, url, kwargs))
        return _response_context(self.response)


def _outbound_request(has_json_body: bool) -> OutboundRequest:
    return OutboundRequest(
        method="POST",
        url="https://api.example.test/items",
        headers={"x-trace": "trace"},
        json_body={"name": "item"},
        has_json_body=has_json_body,
        timeout_seconds=2.5,
        maximum_response_bytes=4,
        approved_hosts=("api.example.test",),
    )


@pytest.mark.asyncio
async def test_specification_fetch_normalizes_exact_host_and_forbids_redirects() -> None:
    client = RecordingAsyncHttpClient(FakeStreamResponse(200, {}, (b"spec",)))
    fetcher = HttpxSpecificationFetcher(client, ExactHttpsDestinationPolicy())

    body = await fetcher.fetch(
        SpecificationFetchRequest(
            url="HTTPS://API.EXAMPLE.TEST/openapi.json",
            approved_hosts=("Api.Example.Test",),
            timeout_seconds=3.5,
        )
    )

    assert body == b"spec"
    assert client.calls == [
        (
            "GET",
            "https://api.example.test/openapi.json",
            {"timeout": 3.5, "follow_redirects": False},
        )
    ]


@pytest.mark.asyncio
async def test_specification_fetch_rejects_non_success_status() -> None:
    fetcher = HttpxSpecificationFetcher(
        RecordingAsyncHttpClient(FakeStreamResponse(302, {}, (b"redirect",))),
        ExactHttpsDestinationPolicy(),
    )
    with pytest.raises(ValueError, match="fetch failed"):
        await fetcher.fetch(
            SpecificationFetchRequest(
                url="https://api.example.test/spec", approved_hosts=("api.example.test",)
            )
        )


@pytest.mark.asyncio
async def test_specification_fetch_rejects_body_above_strict_limit() -> None:
    fetcher = HttpxSpecificationFetcher(
        RecordingAsyncHttpClient(FakeStreamResponse(200, {}, (b"1234", b"5"))),
        ExactHttpsDestinationPolicy(),
    )
    with pytest.raises(ValueError, match="byte limit"):
        await fetcher.fetch(
            SpecificationFetchRequest(
                url="https://api.example.test/spec",
                approved_hosts=("api.example.test",),
                maximum_response_bytes=4,
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("has_json_body", [False, True])
async def test_outbound_transport_forwards_safe_request_arguments(has_json_body: bool) -> None:
    client = RecordingAsyncHttpClient(
        FakeStreamResponse(
            201,
            {
                "Content-Type": " Application/JSON; charset=utf-8 ",
                "ETag": "version",
                "Set-Cookie": "secret",
            },
            (b"1234", b"5"),
        )
    )

    response = await HttpxOutboundOperationAdapter(client).send(_outbound_request(has_json_body))

    assert response.status == 201
    assert response.content_type == "application/json"
    assert response.headers == {"etag": "version"}
    assert response.body == b"1234"
    assert response.truncated is True
    expected_arguments: dict[str, object] = {
        "headers": {"x-trace": "trace"},
        "timeout": 2.5,
        "follow_redirects": False,
    }
    if has_json_body:
        expected_arguments["json"] = {"name": "item"}
    assert client.calls == [("POST", "https://api.example.test/items", expected_arguments)]


@pytest.mark.asyncio
async def test_outbound_transport_replaces_caller_authorization_with_trusted_bearer() -> None:
    client = RecordingAsyncHttpClient(FakeStreamResponse(200, {}, (b"{}",)))
    request_data = _outbound_request(False).model_dump()
    request_data["headers"] = {"Authorization": "Bearer caller-token", "x-trace": "trace"}
    request = AuthenticatedOutboundRequest(
        **request_data,
        authorization=TrustedBearerAuthorization(token=SecretStr("trusted-token")),
    )

    await HttpxOutboundOperationAdapter(client).send(request)

    assert client.calls[0][2]["headers"] == {
        "x-trace": "trace",
        "Authorization": "Bearer trusted-token",
    }


@pytest.mark.asyncio
async def test_outbound_transport_denies_destination_without_streaming() -> None:
    client = RecordingAsyncHttpClient(FakeStreamResponse(200, {}, (b"secret",)))
    request = _outbound_request(False).model_copy(
        update={"url": "http://api.example.test/private?token=query-canary"}
    )

    with pytest.raises(OutboundPolicyError, match="^destination_denied$") as caught:
        await HttpxOutboundOperationAdapter(client).send(request)

    assert client.calls == []
    assert "query-canary" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [300, 301, 302, 307, 308, 399])
async def test_outbound_transport_denies_every_redirect_before_consuming_body(status: int) -> None:
    response = FakeStreamResponse(status, {}, (b"upstream-body-canary",))
    response.aiter_bytes = Mock(side_effect=AssertionError("body consumed"))

    with pytest.raises(OutboundRedirectError, match="^redirect_denied$"):
        await HttpxOutboundOperationAdapter(RecordingAsyncHttpClient(response)).send(
            _outbound_request(False)
        )

    response.aiter_bytes.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_error,expected_error",
    [
        (httpx.ConnectTimeout("url-query-canary"), OutboundTimeoutError),
        (httpx.ReadTimeout("body-canary"), OutboundTimeoutError),
        (httpx.WriteTimeout("credential-canary"), OutboundTimeoutError),
        (httpx.PoolTimeout("header-canary"), OutboundTimeoutError),
        (httpx.ProxyError("raw-upstream-canary"), OutboundNetworkError),
        (httpx.ConnectError("certificate-path-canary"), OutboundNetworkError),
        (httpx.ProtocolError("raw-upstream-canary"), OutboundNetworkError),
    ],
)
async def test_outbound_transport_maps_httpx_errors_to_stable_codes(
    source_error: httpx.HTTPError, expected_error: type[OutboundTransportError]
) -> None:
    with pytest.raises(expected_error) as caught:
        await HttpxOutboundOperationAdapter(RaisingAsyncHttpClient(source_error)).send(
            _outbound_request(False)
        )

    assert str(caught.value) == expected_error.code
    assert caught.value.__cause__ is None
    for canary in (
        "url-query-canary",
        "body-canary",
        "credential-canary",
        "header-canary",
        "certificate-path-canary",
        "raw-upstream-canary",
    ):
        assert canary not in str(caught.value)
        assert canary not in repr(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tls_error", [ssl.SSLError("tls-canary"), ssl.CertificateError("certificate-canary")]
)
async def test_outbound_transport_deterministically_classifies_tls_causes(
    tls_error: BaseException,
) -> None:
    try:
        raise tls_error
    except BaseException as cause:
        try:
            raise httpx.ConnectError("connect-canary") from cause
        except httpx.ConnectError as source_error:
            with pytest.raises(OutboundTlsError, match="^outbound_tls_failed$") as caught:
                await HttpxOutboundOperationAdapter(RaisingAsyncHttpClient(source_error)).send(
                    _outbound_request(False)
                )
    assert caught.value.__cause__ is None
    assert "canary" not in repr(caught.value)


@pytest.mark.asyncio
async def test_outbound_transport_preserves_typed_errors() -> None:
    source_error = OutboundRedirectError()
    with pytest.raises(OutboundRedirectError) as caught:
        await HttpxOutboundOperationAdapter(RaisingAsyncHttpClient(source_error)).send(
            _outbound_request(False)
        )
    assert caught.value is source_error


@pytest.mark.asyncio
async def test_outbound_transport_strips_all_forbidden_headers_case_insensitively() -> None:
    forbidden = HttpxOutboundOperationAdapter._forbidden_request_headers
    headers = {name.swapcase(): "credential-canary" for name in forbidden} | {"X-Safe": "safe"}
    client = RecordingAsyncHttpClient(FakeStreamResponse(200, {}, ()))

    await HttpxOutboundOperationAdapter(client).send(
        _outbound_request(False).model_copy(update={"headers": headers})
    )

    assert client.calls[0][2]["headers"] == {"X-Safe": "safe"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers,expected_content_type",
    [
        ({}, ""),
        ({"Content-Type": "application/json"}, "application/json"),
        ({"CONTENT-TYPE": " Text/Plain ; Charset=UTF-8 "}, "text/plain"),
    ],
)
async def test_outbound_transport_normalizes_content_type(
    headers: dict[str, str], expected_content_type: str
) -> None:
    response = await HttpxOutboundOperationAdapter(
        RecordingAsyncHttpClient(FakeStreamResponse(200, headers, ()))
    ).send(_outbound_request(False))
    assert response.content_type == expected_content_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks,expected_body,expected_truncated",
    [
        ((b"1234",), b"1234", False),
        ((b"12345",), b"1234", True),
        ((b"12", b"345"), b"1234", True),
        ((), b"", False),
        ((b"",), b"", False),
    ],
)
async def test_outbound_transport_enforces_response_limit(
    chunks: tuple[bytes, ...], expected_body: bytes, expected_truncated: bool
) -> None:
    response = await HttpxOutboundOperationAdapter(
        RecordingAsyncHttpClient(FakeStreamResponse(200, {}, chunks))
    ).send(_outbound_request(False))
    assert response.body == expected_body
    assert response.truncated is expected_truncated


@pytest.mark.asyncio
async def test_outbound_transport_returns_only_allowlisted_normalized_response_headers() -> None:
    headers = {
        name.swapcase(): name for name in HttpxOutboundOperationAdapter._safe_response_headers
    } | {"Set-Cookie": "credential-canary", "Content-Type": "text/plain"}
    response = await HttpxOutboundOperationAdapter(
        RecordingAsyncHttpClient(FakeStreamResponse(200, headers, ()))
    ).send(_outbound_request(False))
    assert response.headers == {
        name: name for name in HttpxOutboundOperationAdapter._safe_response_headers
    }


def test_outbound_http_client_factory_configures_hardened_client() -> None:
    factory = OutboundHttpClientFactory(1.0, 2.0, 3.0, 4.0)
    with patch(
        "umbod.core.connectors.openapi.execution.http_adapters.httpx.AsyncClient"
    ) as client_type:
        factory.create()
    arguments = client_type.call_args.kwargs
    assert arguments == {
        "trust_env": False,
        "follow_redirects": False,
        "timeout": arguments["timeout"],
    }
    assert arguments["timeout"] == httpx.Timeout(connect=1.0, read=2.0, write=3.0, pool=4.0)


@pytest.mark.parametrize(
    "url,approved_hosts",
    [
        ("https://api.example.test", ()),
        ("https://api.example.test", ("",)),
        ("https://api.example.test", ("*.example.test",)),
        ("https://api.example.test", ("api.example.test/path",)),
        ("https://sub.api.example.test", ("api.example.test",)),
        ("https://user@api.example.test", ("api.example.test",)),
        ("https://api.example.test/path#fragment", ("api.example.test",)),
        ("http://api.example.test", ("api.example.test",)),
        ("https://api.example.test:444", ("api.example.test",)),
        ("https://127.0.0.1", ("127.0.0.1",)),
        ("https://localhost", ("localhost",)),
        ("https://internal", ("internal",)),
        ("https://api.example.test.", ("api.example.test",)),
        ("https://éxample.test", ("éxample.test",)),
        ("https://api.example.test", ("other.example.test",)),
    ],
)
def test_destination_policy_rejects_unsafe_or_non_exact_hosts(
    url: str, approved_hosts: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError):
        ExactHttpsDestinationPolicy().validate(url, approved_hosts)


@pytest.mark.parametrize("model", [SpecificationFetchRequest, OutboundRequest])
def test_http_boundary_models_reject_non_positive_limits(model: type[object]) -> None:
    values: dict[str, object]
    if model is SpecificationFetchRequest:
        values = {
            "url": "https://api.example.test/spec",
            "approved_hosts": ("api.example.test",),
            "maximum_response_bytes": 0,
        }
    else:
        values = {
            "method": "GET",
            "url": "https://api.example.test",
            "headers": {},
            "json_body": {},
            "has_json_body": False,
            "timeout_seconds": 1.0,
            "maximum_response_bytes": 0,
            "approved_hosts": ("api.example.test",),
        }
    with pytest.raises(ValidationError):
        model(**values)
