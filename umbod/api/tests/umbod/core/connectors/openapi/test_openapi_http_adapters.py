import ssl
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import AsyncIterator
from unittest.mock import Mock

import pytest
from pydantic import SecretStr, ValidationError

from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureOrigin,
    current_invocation_failure,
    invocation_failure_scope,
)
from umbod.core.connectors.openapi.execution import (
    AuthenticatedOutboundRequest,
    ExactHttpsDestinationPolicy,
    OutboundNetworkError,
    OutboundOperationTransport,
    OutboundPolicyError,
    OutboundRedirectError,
    OutboundRequest,
    OutboundTimeoutError,
    OutboundTlsError,
    OutboundTransportError,
    SpecificationFetchRequest,
    StreamingOutboundOperationAdapter,
    StreamingSpecificationFetcher,
    TrustedBearerAuthorization,
)
from umbod.core.network.http import (
    HttpRedirectPolicy,
    HttpRequest,
    HttpTimeoutError,
    HttpTlsError,
    HttpTransportError,
    JsonHttpBody,
    NoHttpBody,
)


class FakeStreamResponse:
    def __init__(self, status: int, headers: dict[str, str], chunks: tuple[bytes, ...]) -> None:
        self.status_code = status
        self.headers: Mapping[str, str] = headers
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

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[FakeStreamResponse]:
        self.calls += 1

        @asynccontextmanager
        async def raising_context() -> AsyncIterator[FakeStreamResponse]:
            raise self._error
            yield FakeStreamResponse(200, {}, ())

        return raising_context()

    async def aclose(self) -> None:
        return None


class RecordingAsyncHttpClient:
    def __init__(self, response: FakeStreamResponse) -> None:
        self.response = response
        self.calls: list[HttpRequest] = []

    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[FakeStreamResponse]:
        self.calls.append(request)
        return _response_context(self.response)

    async def aclose(self) -> None:
        return None


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
    fetcher = StreamingSpecificationFetcher(client, ExactHttpsDestinationPolicy())

    body = await fetcher.fetch(
        SpecificationFetchRequest(
            url="HTTPS://API.EXAMPLE.TEST/openapi.json",
            approved_hosts=("Api.Example.Test",),
            timeout_seconds=3.5,
        )
    )

    assert body == b"spec"
    request, = client.calls
    assert request.method == "GET"
    assert request.url == "https://api.example.test/openapi.json"
    assert request.headers == {}
    assert request.query == {}
    assert isinstance(request.body, NoHttpBody)
    assert request.timeout == 3.5
    assert request.redirects is HttpRedirectPolicy.DENY


@pytest.mark.asyncio
async def test_specification_fetch_rejects_non_success_status() -> None:
    fetcher = StreamingSpecificationFetcher(
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
    fetcher = StreamingSpecificationFetcher(
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

    response = await StreamingOutboundOperationAdapter(client).send(_outbound_request(has_json_body))

    assert response.status == 201
    assert response.content_type == "application/json"
    assert response.headers == {"etag": "version"}
    assert response.body == b"1234"
    assert response.truncated is True
    request, = client.calls
    assert request.method == "POST"
    assert request.url == "https://api.example.test/items"
    assert request.headers == {"x-trace": "trace"}
    assert request.query == {}
    assert request.body == (JsonHttpBody(value={"name": "item"}) if has_json_body else NoHttpBody())
    assert request.timeout == 2.5
    assert request.redirects is HttpRedirectPolicy.DENY


@pytest.mark.asyncio
async def test_outbound_transport_replaces_caller_authorization_with_trusted_bearer() -> None:
    client = RecordingAsyncHttpClient(FakeStreamResponse(200, {}, (b"{}",)))
    request_data = _outbound_request(False).model_dump()
    request_data["headers"] = {"Authorization": "Bearer caller-token", "x-trace": "trace"}
    request = AuthenticatedOutboundRequest(
        **request_data,
        authorization=TrustedBearerAuthorization(token=SecretStr("trusted-token")),
    )

    await StreamingOutboundOperationAdapter(client).send(request)

    assert client.calls[0].headers == {
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
        await StreamingOutboundOperationAdapter(client).send(request)

    assert client.calls == []
    assert "query-canary" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [300, 301, 302, 307, 308, 399])
async def test_outbound_transport_denies_every_redirect_before_consuming_body(status: int) -> None:
    response = FakeStreamResponse(status, {}, (b"upstream-body-canary",))
    response.aiter_bytes = Mock(side_effect=AssertionError("body consumed"))

    with pytest.raises(OutboundRedirectError, match="^redirect_denied$"):
        await StreamingOutboundOperationAdapter(RecordingAsyncHttpClient(response)).send(
            _outbound_request(False)
        )

    response.aiter_bytes.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_error,expected_error",
    [
        (HttpTimeoutError("url-query-canary"), OutboundTimeoutError),
        (HttpTimeoutError("body-canary"), OutboundTimeoutError),
        (HttpTimeoutError("credential-canary"), OutboundTimeoutError),
        (HttpTimeoutError("header-canary"), OutboundTimeoutError),
        (HttpTransportError("raw-upstream-canary"), OutboundNetworkError),
        (HttpTransportError("certificate-path-canary"), OutboundNetworkError),
        (HttpTlsError("tls-canary"), OutboundTlsError),
    ],
)
async def test_outbound_transport_maps_neutral_http_errors_to_stable_codes(
    source_error: HttpTransportError, expected_error: type[OutboundTransportError]
) -> None:
    with invocation_failure_scope():
        with pytest.raises(expected_error) as caught:
            transport: OutboundOperationTransport = StreamingOutboundOperationAdapter(
                RaisingAsyncHttpClient(source_error)
            )
            await transport.send(_outbound_request(False))
        evidence = current_invocation_failure()

    assert isinstance(evidence, InvocationExceptionEvidence)
    assert evidence.origin == InvocationFailureOrigin.OPENAPI
    assert evidence.exception_type == type(source_error).__qualname__
    assert "raising_context" in evidence.stacktrace
    assert "canary" not in evidence.stacktrace
    assert str(caught.value) == expected_error.code
    assert caught.value.__cause__ is None
    for canary in (
        "url-query-canary",
        "body-canary",
        "credential-canary",
        "header-canary",
        "certificate-path-canary",
        "raw-upstream-canary",
        "tls-canary",
    ):
        assert canary not in str(caught.value)
        assert canary not in repr(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tls_error", [ssl.SSLError("tls-canary"), ssl.CertificateError("certificate-canary")]
)
async def test_outbound_tls_failure_captures_underlying_cause_as_evidence(
    tls_error: ssl.SSLError,
) -> None:
    with invocation_failure_scope():
        try:
            raise tls_error
        except ssl.SSLError as cause:
            try:
                raise HttpTlsError("connect-canary") from cause
            except HttpTlsError as source_error:
                transport = StreamingOutboundOperationAdapter(RaisingAsyncHttpClient(source_error))
                with pytest.raises(OutboundTlsError, match="^outbound_tls_failed$") as caught:
                    await transport.send(_outbound_request(False))
        evidence = current_invocation_failure()

    assert isinstance(evidence, InvocationExceptionEvidence)
    assert evidence.origin == InvocationFailureOrigin.OPENAPI
    assert evidence.exception_type == type(tls_error).__qualname__
    assert "canary" not in evidence.stacktrace
    assert caught.value.__cause__ is None
    assert "canary" not in repr(caught.value)


@pytest.mark.asyncio
async def test_outbound_transport_preserves_typed_errors() -> None:
    source_error = OutboundRedirectError()
    with pytest.raises(OutboundRedirectError) as caught:
        await StreamingOutboundOperationAdapter(RaisingAsyncHttpClient(source_error)).send(
            _outbound_request(False)
        )
    assert caught.value is source_error


@pytest.mark.asyncio
async def test_outbound_transport_strips_all_forbidden_headers_case_insensitively() -> None:
    forbidden = (
        "authorization",
        "cookie",
        "proxy-authorization",
        "host",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
    )
    headers = {name.swapcase(): "credential-canary" for name in forbidden} | {"X-Safe": "safe"}
    client = RecordingAsyncHttpClient(FakeStreamResponse(200, {}, ()))

    transport: OutboundOperationTransport = StreamingOutboundOperationAdapter(client)
    await transport.send(_outbound_request(False).model_copy(update={"headers": headers}))

    assert client.calls[0].headers == {"X-Safe": "safe"}


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
    response = await StreamingOutboundOperationAdapter(
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
    response = await StreamingOutboundOperationAdapter(
        RecordingAsyncHttpClient(FakeStreamResponse(200, {}, chunks))
    ).send(_outbound_request(False))
    assert response.body == expected_body
    assert response.truncated is expected_truncated


@pytest.mark.asyncio
async def test_outbound_transport_returns_only_allowlisted_normalized_response_headers() -> None:
    expected_headers = {
        "cache-control": "cache-control",
        "content-language": "content-language",
        "etag": "etag",
        "expires": "expires",
        "last-modified": "last-modified",
        "retry-after": "retry-after",
    }
    headers = {name.swapcase(): value for name, value in expected_headers.items()} | {
        "Set-Cookie": "credential-canary",
        "Content-Type": "text/plain",
        "X-Unexpected": "unexpected-canary",
    }
    transport: OutboundOperationTransport = StreamingOutboundOperationAdapter(
        RecordingAsyncHttpClient(FakeStreamResponse(200, headers, ()))
    )
    response = await transport.send(_outbound_request(False))
    assert response.headers == expected_headers


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
