import socket
from typing import cast
from unittest.mock import AsyncMock

import httpcore
import pytest

from umbod.core.network import PublicAddressNetworkBackend


@pytest.mark.parametrize("addresses", [["8.8.8.8", "127.0.0.1"], ["10.0.0.1", "8.8.8.8"], ["8.8.8.8", "::1"], ["169.254.169.254"], ["::ffff:8.8.8.8"], []])
@pytest.mark.asyncio
async def test_dns_with_any_nonpublic_address_is_rejected_before_connecting(monkeypatch: pytest.MonkeyPatch, addresses: list[str]) -> None:
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]
    resolver = AsyncMock(return_value=answers)
    monkeypatch.setattr("umbod.core.network.adapters.anyio.getaddrinfo", resolver)
    transport = AsyncMock(spec=httpcore.AsyncNetworkBackend)
    backend: httpcore.AsyncNetworkBackend = PublicAddressNetworkBackend(transport)
    with pytest.raises(ValueError):
        await backend.connect_tcp("example.com", 443, 1.0, None, None)
    transport.connect_tcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_pins_validated_address_instead_of_resolving_hostname_again(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = AsyncMock(return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
    ])
    monkeypatch.setattr("umbod.core.network.adapters.anyio.getaddrinfo", resolver)
    stream = cast(httpcore.AsyncNetworkStream, object())
    transport = AsyncMock(spec=httpcore.AsyncNetworkBackend)
    transport.connect_tcp.return_value = stream
    backend: httpcore.AsyncNetworkBackend = PublicAddressNetworkBackend(transport)
    result = await backend.connect_tcp("example.com", 443, 1.0, None, None)
    assert result is stream
    resolver.assert_awaited_once_with("example.com", 443, type=socket.SOCK_STREAM)
    transport.connect_tcp.assert_awaited_once_with(host="8.8.8.8", port=443, timeout=1.0, local_address=None, socket_options=None)


@pytest.mark.asyncio
async def test_dns_failure_does_not_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("umbod.core.network.adapters.anyio.getaddrinfo", AsyncMock(side_effect=socket.gaierror("not found")))
    transport = AsyncMock(spec=httpcore.AsyncNetworkBackend)
    backend: httpcore.AsyncNetworkBackend = PublicAddressNetworkBackend(transport)
    with pytest.raises(socket.gaierror):
        await backend.connect_tcp("example.com", 443, 1.0, None, None)
    transport.connect_tcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_unix_socket_is_rejected_without_delegating() -> None:
    transport = AsyncMock(spec=httpcore.AsyncNetworkBackend)
    backend: httpcore.AsyncNetworkBackend = PublicAddressNetworkBackend(transport)
    with pytest.raises(ValueError):
        await backend.connect_unix_socket("/tmp/socket", 1.0, None)
    transport.connect_unix_socket.assert_not_awaited()
