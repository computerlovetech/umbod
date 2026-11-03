from .contracts import LOOKUP_FINGERPRINT
import json
import ssl
from collections.abc import Iterable
from datetime import datetime, timezone

import anyio
import httpcore2
import pytest
from anyio.abc import SocketAttribute, SocketStream

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import FastMCPPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport

from .conftest import ScriptedNetwork, ScriptedResolver, ScriptedStream


class LocalTestStream(httpcore2.AsyncNetworkStream):
    def __init__(self, delegate: httpcore2.AsyncNetworkStream) -> None:
        self.delegate = delegate

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self.delegate.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self.delegate.write(buffer, timeout)

    async def aclose(self) -> None:
        await self.delegate.aclose()

    async def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert server_hostname == "public.example"
        return self


class LocalTestNetwork(httpcore2.AsyncNetworkBackend):
    def __init__(self, port: int) -> None:
        self.port = port

    async def connect_tcp(
        self, host: str, port: int, timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        assert host == "8.8.8.8"
        delegate = await httpcore2.AnyIOBackend().connect_tcp("127.0.0.1", self.port, timeout)
        return LocalTestStream(delegate)

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)


@pytest.mark.asyncio
@pytest.mark.parametrize("oversized", [False, True])
async def test_real_local_tcp_streaming_via_injected_network_only(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, oversized: bool) -> None:
    protocol = ScriptedNetwork()
    if oversized:
        protocol.call_result = {"content": [{"type": "text", "text": "x" * 500}]}
        limits = limits.model_copy(update={"maximum_response_bytes": 256})

    async def serve(stream: SocketStream) -> None:
        parser = ScriptedStream(protocol)
        async with stream:
            while not parser.ready.is_set():
                await parser.write(await stream.receive())
            header, body = parser.reply.split(b"\r\n\r\n", 1)
            message = protocol.requests[-1][2]
            if message.get("method") == "tools/call":
                payload = b"data: " + body + b"\n\n"
                header = b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\ntransfer-encoding: chunked\r\n\r\n"
                await stream.send(header)
                for offset in range(0, len(payload), 7):
                    chunk = payload[offset:offset + 7]
                    try:
                        await stream.send(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    except anyio.BrokenResourceError:
                        return
                    await anyio.lowlevel.checkpoint()
                try:
                    await stream.send(b"0\r\n\r\n")
                except anyio.BrokenResourceError:
                    return
            else:
                await stream.send(header + b"\r\n\r\n" + body)

    listener = await anyio.create_tcp_listener(local_host="127.0.0.1")
    port = listener.extra(SocketAttribute.local_port)
    transport: PersonalMcpTransport = FastMCPPersonalMcpTransport(
        limits, lambda: datetime.now(timezone.utc), ScriptedResolver(), lambda: LocalTestNetwork(port), ssl.create_default_context(),
    )
    async with listener, anyio.create_task_group() as tasks:
        tasks.start_soon(listener.serve, serve)
        command = PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={})
        if oversized:
            with pytest.raises(PersonalRuntimeUnavailable):
                await transport.call_tool(command)
        else:
            result = await transport.call_tool(command)
            assert result.result["content"] == [{"type": "text", "text": "done"}]
            assert target.access_token.get_secret_value() not in json.dumps(result.result)
        tasks.cancel_scope.cancel()
