import socket
import ssl
from collections.abc import Iterable
from typing import Optional

import anyio
import httpcore
import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.network import (
    PublicAddressNetworkBackend,
    SafeOAuthHttpTransport,
    public_connection_pool,
)
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import (
    OAuthDestination,
    OAuthHttpRequest,
    OAuthHttpTransport,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure


class MemoryStream(httpcore.AsyncNetworkStream):
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.written = bytearray()
        self.server_hostname: Optional[str] = None
        self.ssl_context: Optional[ssl.SSLContext] = None
        self.closed = False

    async def read(self, max_bytes: int, timeout: Optional[float]) -> bytes:
        content, self.content = self.content[:max_bytes], self.content[max_bytes:]
        return content

    async def write(self, buffer: bytes, timeout: Optional[float]) -> None:
        self.written.extend(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: Optional[str], timeout: Optional[float],
    ) -> httpcore.AsyncNetworkStream:
        self.server_hostname = server_hostname
        self.ssl_context = ssl_context
        return self

    def get_extra_info(self, info: str) -> object:
        return None


class MemoryNetwork(httpcore.AsyncNetworkBackend):
    def __init__(self, stream: MemoryStream) -> None:
        self.stream = stream
        self.targets: list[tuple[str, int]] = []

    async def connect_tcp(
        self, host: str, port: int, timeout: Optional[float], local_address: Optional[str],
        socket_options: Optional[Iterable[tuple[int, int, object]]],
    ) -> httpcore.AsyncNetworkStream:
        self.targets.append((host, port))
        return self.stream

    async def connect_unix_socket(
        self, path: str, timeout: Optional[float], socket_options: Optional[Iterable[tuple[int, int, object]]],
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError("Unexpected Unix socket")

    async def sleep(self, seconds: float) -> None:
        raise AssertionError("Unexpected retry")


def request(url: str) -> OAuthHttpRequest:
    return OAuthHttpRequest(method="POST", url=url, content_type="application/json", body=SecretStr("{}"))


@pytest.mark.asyncio
async def test_connect_time_resolution_pins_literal_address_and_preserves_tls_hostname(public_dns: list[str]) -> None:
    stream = MemoryStream(content=b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
    network = MemoryNetwork(stream=stream)
    async with httpcore.AsyncConnectionPool(
        network_backend=PublicAddressNetworkBackend(backend=network), ssl_context=ssl.create_default_context(), retries=0,
    ) as pool:
        transport: OAuthHttpTransport = SafeOAuthHttpTransport(pool=pool)
        result = await transport.request(request("https://issuer.example/token"))
    assert result.status == 200
    assert result.body == b"{}"
    assert public_dns == ["issuer.example"]
    assert network.targets == [("93.184.216.34", 443)]
    assert stream.server_hostname == "issuer.example"
    assert stream.ssl_context is not None
    assert stream.ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert stream.ssl_context.check_hostname
    assert b"Host: issuer.example" in stream.written


@pytest.mark.asyncio
@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.0.1", "169.254.169.254", "0.0.0.0",
    "192.0.2.1", "224.0.0.1", "240.0.0.1", "::1", "fc00::1", "fe80::1", "2001:db8::1",
    "::ffff:93.184.216.34", "::ffff:127.0.0.1", "ff02::1",
])
async def test_any_nonpublic_dns_answer_blocks_entire_connection(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    async def resolve(host: str, port: int, *, type: int) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, port)),
        ]

    monkeypatch.setattr(anyio, "getaddrinfo", resolve)
    network = MemoryNetwork(stream=MemoryStream(content=b""))
    backend: httpcore.AsyncNetworkBackend = PublicAddressNetworkBackend(backend=network)
    with pytest.raises(ValueError, match="Nonpublic address"):
        await backend.connect_tcp(host="issuer.example", port=443, timeout=1.0, local_address=None, socket_options=None)
    assert not network.targets


@pytest.mark.asyncio
async def test_each_new_connection_resolves_again_and_rebinding_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def resolve(host: str, port: int, *, type: int) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        nonlocal calls
        calls += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34" if calls == 1 else "127.0.0.1", port))]

    monkeypatch.setattr(anyio, "getaddrinfo", resolve)
    network = MemoryNetwork(stream=MemoryStream(content=b""))
    backend: httpcore.AsyncNetworkBackend = PublicAddressNetworkBackend(backend=network)
    await backend.connect_tcp(host="issuer.example", port=443, timeout=1.0, local_address=None, socket_options=None)
    with pytest.raises(ValueError):
        await backend.connect_tcp(host="issuer.example", port=443, timeout=1.0, local_address=None, socket_options=None)
    assert network.targets == [("93.184.216.34", 443)]


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    b"HTTP/1.1 302 Found\r\nLocation: https://private.example\r\nContent-Length: 0\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Length: 1048577\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n100001\r\n" + b"x" * 1_048_577 + b"\r\n0\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 2\r\n\r\n{}",
    b"HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\nshort",
])
async def test_transport_rejects_redirects_oversized_and_invalid_responses_without_retries(content: bytes, public_dns: list[str]) -> None:
    stream = MemoryStream(content=content)
    network = MemoryNetwork(stream=stream)
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(backend=network), retries=0) as pool:
        transport: OAuthHttpTransport = SafeOAuthHttpTransport(pool=pool)
        with pytest.raises(PersonalOAuthProviderFailure) as caught:
            await transport.request(request("https://issuer.example/token"))
    assert str(caught.value) == "Personal OAuth provider request failed"
    assert len(network.targets) == 1
    assert stream.closed


@pytest.mark.asyncio
async def test_transport_accepts_exact_body_budget(public_dns: list[str]) -> None:
    content = b"x" * 1_048_576
    stream = MemoryStream(content=b"HTTP/1.1 200 OK\r\nContent-Length: 1048576\r\n\r\n" + content)
    network = MemoryNetwork(stream=stream)
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(backend=network)) as pool:
        transport: OAuthHttpTransport = SafeOAuthHttpTransport(pool=pool)
        result = await transport.request(request("https://issuer.example/token"))
    assert result.body == content


@pytest.mark.asyncio
async def test_authorization_destination_is_public_dns_validated_without_connecting(public_dns: list[str]) -> None:
    async with public_connection_pool() as pool:
        transport: OAuthHttpTransport = SafeOAuthHttpTransport(pool=pool)
        await transport.validate_destination(OAuthDestination(url="https://issuer.example/authorize"))
    assert public_dns == ["issuer.example"]


@pytest.mark.asyncio
async def test_dns_failure_is_fixed_secret_free_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(host: str, port: int, *, type: int) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        raise OSError("sensitive-provider-hostname")

    monkeypatch.setattr(anyio, "getaddrinfo", resolve)
    async with public_connection_pool() as pool:
        transport: OAuthHttpTransport = SafeOAuthHttpTransport(pool=pool)
        with pytest.raises(PersonalOAuthProviderFailure) as caught:
            await transport.validate_destination(OAuthDestination(url="https://issuer.example/authorize"))
    assert str(caught.value) == "Personal OAuth provider request failed"


@pytest.mark.asyncio
async def test_private_literal_fails_without_dns_or_connection(public_dns: list[str]) -> None:
    async with public_connection_pool() as pool:
        transport: OAuthHttpTransport = SafeOAuthHttpTransport(pool=pool)
        with pytest.raises(PersonalOAuthProviderFailure):
            await transport.request(request("https://127.0.0.1/mcp"))
    assert not public_dns
