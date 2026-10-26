import ipaddress
import socket
import ssl
from collections.abc import Iterable
from typing import Optional

import anyio
import httpcore


def validate_public_address(literal: str) -> str:
    address = ipaddress.ip_address(literal)
    if (
        not address.is_global
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
        or getattr(address, "ipv4_mapped", None) is not None
        or "%" in literal
    ):
        raise ValueError("Nonpublic address")
    return literal


async def resolve_public_addresses(host: str, port: int) -> list[str]:
    answers = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = [validate_public_address(str(answer[4][0])) for answer in answers]
    if not addresses:
        raise ValueError("No public address")
    return addresses


class PublicAddressNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, backend: httpcore.AsyncNetworkBackend) -> None:
        self._backend = backend

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float],
        local_address: Optional[str],
        socket_options: Optional[Iterable[tuple[int, int, object]]],
    ) -> httpcore.AsyncNetworkStream:
        with anyio.fail_after(timeout):
            addresses = await resolve_public_addresses(host, port)
            return await self._backend.connect_tcp(
                host=addresses[0],
                port=port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float],
        socket_options: Optional[Iterable[tuple[int, int, object]]],
    ) -> httpcore.AsyncNetworkStream:
        raise ValueError("Unix sockets are unsupported")

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)


def public_http_connection_pool(max_connections: int) -> httpcore.AsyncConnectionPool:
    if max_connections <= 0:
        raise ValueError("Connection limit must be positive")
    return httpcore.AsyncConnectionPool(
        ssl_context=ssl.create_default_context(),
        proxy=None,
        network_backend=PublicAddressNetworkBackend(httpcore.AnyIOBackend()),
        retries=0,
        max_connections=max_connections,
        max_keepalive_connections=0,
    )
