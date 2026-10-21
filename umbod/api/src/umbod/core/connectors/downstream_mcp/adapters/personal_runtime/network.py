import socket
import ssl
from collections.abc import Callable, Iterable
from ipaddress import ip_address
from typing import Protocol

import anyio
import httpcore2
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable


class PublicAddressResolver(Protocol):
    async def resolve(self, host: str, port: int) -> tuple[str, ...]: ...


class SystemAddressResolver:
    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        records = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return tuple(str(record[4][0]) for record in records)


class PinnedPublicNetworkBackend(httpcore2.AsyncNetworkBackend):
    def __init__(self, resolver: PublicAddressResolver, backend: httpcore2.AsyncNetworkBackend, check: Callable[[], None], token: SecretStr) -> None:
        self._resolver = resolver
        self._backend = backend
        self._check = check
        self._token = token

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        self._check()
        addresses = await self._resolver.resolve(host, port)
        self._check()
        if not addresses:
            raise PersonalRuntimeUnavailable("Personal MCP unavailable")
        for address in addresses:
            parsed = ip_address(address)
            if (
                not parsed.is_global or parsed.is_multicast or parsed.is_reserved
                or getattr(parsed, "ipv4_mapped", None) is not None or "%" in address
            ):
                raise PersonalRuntimeUnavailable("Personal MCP unavailable")
        stream = await self._backend.connect_tcp(
            addresses[0], port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )
        return CheckedNetworkStream(stream, self._check, self._token)

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise PersonalRuntimeUnavailable("Personal MCP unavailable")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class CheckedNetworkStream(httpcore2.AsyncNetworkStream):
    def __init__(self, stream: httpcore2.AsyncNetworkStream, check: Callable[[], None], token: SecretStr) -> None:
        self._stream = stream
        self._check = check
        self._token = token
        self._secret_bytes = token.get_secret_value().encode("ascii")
        self._trailer = b""

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        self._check()
        result = await self._stream.read(max_bytes, timeout)
        self._check()
        combined = self._trailer + result
        if self._secret_bytes in combined:
            raise PersonalRuntimeUnavailable("Personal MCP unavailable") from None
        self._trailer = combined[-max(0, len(self._secret_bytes) - 1):] if len(self._secret_bytes) > 1 else b""
        return result

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._check()
        await self._stream.write(buffer, timeout)
        self._check()

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        self._check()
        if not ssl_context.check_hostname or ssl_context.verify_mode != ssl.CERT_REQUIRED:
            raise PersonalRuntimeUnavailable("Personal MCP unavailable")
        secured = await self._stream.start_tls(ssl_context, server_hostname, timeout)
        return CheckedNetworkStream(secured, self._check, self._token)

    def get_extra_info(self, info: str) -> object:
        return self._stream.get_extra_info(info)
