import json
import socket
import ssl
from unittest.mock import AsyncMock

import anyio
import httpcore
import pytest

from umbod.core.connectors.downstream_mcp.endpoint_access import (
    AnonymousAccessRejected,
    AnonymousInitializationResult,
    AnonymousInitializationSucceeded,
    CheckMcpEndpointAccess,
    EndpointAccessInconclusive,
)
from umbod.core.network import public_http_connection_pool
from umbod.infrastructure.mcp_endpoint_access import open_anonymous_mcp_initialization
from umbod.infrastructure.mcp_endpoint_access.adapter import PublicMcpInitialization

_ENDPOINT = CheckMcpEndpointAccess(endpoint_url="https://mcp.example/remote")
_MESSAGE = (
    b'{"jsonrpc":"2.0","id":"umbod-initialize","result":'
    b'{"protocolVersion":"2025-11-25","capabilities":{},'
    b'"serverInfo":{"name":"example","version":"1"}}}'
)


def _json_response(payload: bytes) -> list[bytes]:
    return [
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
        + str(len(payload)).encode("ascii")
        + b"\r\n\r\n",
        payload,
    ]


async def _initialize(
    pieces: list[bytes], maximum_response_bytes: int = 1024
) -> AnonymousInitializationResult:
    async with httpcore.AsyncConnectionPool(
        network_backend=httpcore.AsyncMockBackend(pieces)
    ) as pool:
        return await PublicMcpInitialization(
            pool, timeout_seconds=1, maximum_response_bytes=maximum_response_bytes
        ).initialize(_ENDPOINT)


@pytest.mark.asyncio
async def test_factory_pins_connection_and_sends_only_anonymous_initialize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve = AsyncMock(
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))]
    )
    backend = AsyncMock(spec=httpcore.AsyncNetworkBackend)
    stream = AsyncMock(spec=httpcore.AsyncNetworkStream)
    stream.read.side_effect = _json_response(_MESSAGE)
    stream.start_tls.return_value = stream
    stream.get_extra_info.return_value = None
    backend.connect_tcp.return_value = stream
    monkeypatch.setattr(anyio, "getaddrinfo", resolve)
    monkeypatch.setattr(httpcore, "AnyIOBackend", lambda: backend)
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.example")
    monkeypatch.setenv("ALL_PROXY", "https://proxy.example")

    async with open_anonymous_mcp_initialization() as initialization:
        outcome = await initialization.initialize(_ENDPOINT)

    assert outcome == AnonymousInitializationSucceeded()
    resolve.assert_awaited_once_with("mcp.example", 443, type=socket.SOCK_STREAM)
    backend.connect_tcp.assert_awaited_once()
    assert backend.connect_tcp.await_args.kwargs["host"] == "1.1.1.1"
    stream.start_tls.assert_awaited_once()
    assert stream.start_tls.await_args.kwargs["server_hostname"] == "mcp.example"
    context = stream.start_tls.await_args.kwargs["ssl_context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    written = b"".join(call.args[0] for call in stream.write.await_args_list)
    headers, _, body = written.partition(b"\r\n\r\n")
    assert headers.startswith(b"POST /remote HTTP/1.1\r\n")
    assert b"\r\nhost: mcp.example\r\n" in headers.lower()
    assert b"\r\nauthorization:" not in headers.lower()
    assert b"\r\nproxy-authorization:" not in headers.lower()
    assert b"\r\ncookie:" not in headers.lower()
    assert json.loads(body) == {
        "jsonrpc": "2.0",
        "id": "umbod-initialize",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "umbod-endpoint-check", "version": "1"},
        },
    }


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AnonymousAccessRejected(status_code=401)),
        (403, AnonymousAccessRejected(status_code=403)),
        (302, EndpointAccessInconclusive(reason="redirected")),
        (404, EndpointAccessInconclusive(reason="endpoint_not_found")),
        (500, EndpointAccessInconclusive(reason="unreachable")),
    ],
)
@pytest.mark.asyncio
async def test_status_is_classified_without_reading_response_body(
    status: int, expected: AnonymousInitializationResult
) -> None:
    outcome = await _initialize(
        [
            f"HTTP/1.1 {status} Status\r\nContent-Length: 100\r\nLocation: https://moved.example\r\n\r\n".encode(
                "ascii"
            )
        ]
    )

    assert outcome == expected


@pytest.mark.parametrize(
    "body",
    [
        b"not JSON",
        _MESSAGE.replace(b"umbod-initialize", b"unrelated-request"),
        _MESSAGE.replace(b"2025-11-25", b"unknown"),
        _MESSAGE.replace(b'"capabilities":{}', b'"capabilities":null'),
        _MESSAGE.replace(b'"result":', b'"error":null,"result":'),
        _MESSAGE.replace(b'"result":', b'"id":123,"result":'),
    ],
)
@pytest.mark.asyncio
async def test_invalid_initialize_response_is_inconclusive(body: bytes) -> None:
    assert await _initialize(_json_response(body)) == EndpointAccessInconclusive(
        reason="invalid_mcp_protocol"
    )


@pytest.mark.asyncio
async def test_event_stream_stops_at_matching_response_without_waiting_for_eof() -> (
    None
):
    outcome = await _initialize(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream; charset=utf-8\r\n"
            b"Content-Length: 1000\r\n\r\n",
            b": heartbeat\r",
            b'\n\r\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\r\n\r\n',
            b"event: message\ndata: " + _MESSAGE + b"\r\r",
        ]
    )

    assert outcome == AnonymousInitializationSucceeded()


@pytest.mark.parametrize("content_type", [b"application/json", b"text/event-stream"])
@pytest.mark.asyncio
async def test_unframed_body_cannot_exceed_read_limit(content_type: bytes) -> None:
    outcome = await _initialize(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: " + content_type + b"\r\n\r\n",
            b" " * 30,
            b" " * 30,
        ],
        maximum_response_bytes=40,
    )

    assert outcome == EndpointAccessInconclusive(reason="response_too_large")


@pytest.mark.asyncio
async def test_declared_oversize_is_rejected_without_waiting_for_body() -> None:
    outcome = await _initialize(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2000\r\n\r\n"
        ]
    )

    assert outcome == EndpointAccessInconclusive(reason="response_too_large")


@pytest.mark.asyncio
async def test_compressed_response_is_not_decoded() -> None:
    outcome = await _initialize(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Encoding: gzip\r\n\r\n"
        ]
    )

    assert outcome == EndpointAccessInconclusive(reason="invalid_mcp_protocol")


@pytest.mark.asyncio
async def test_overall_deadline_includes_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stalled_resolution(
        host: str, port: int, *, type: socket.SocketKind
    ) -> None:
        await anyio.sleep_forever()

    monkeypatch.setattr(anyio, "getaddrinfo", stalled_resolution)

    async with public_http_connection_pool(max_connections=1) as pool:
        outcome = await PublicMcpInitialization(
            pool, timeout_seconds=0.01, maximum_response_bytes=1024
        ).initialize(_ENDPOINT)

    assert outcome == EndpointAccessInconclusive(reason="timeout")
