import json
import ssl
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

import anyio
import httpcore2
import pytest

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import FastMCPPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal, PersonalConnectionKey
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget


class ScriptedResolver:
    def __init__(self, addresses: tuple[str, ...] = ("8.8.8.8",)) -> None:
        self.addresses = addresses
        self.lookups: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        self.lookups.append((host, port))
        return self.addresses


class ScriptedNetwork(httpcore2.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connections: list[str] = []
        self.sni: list[str] = []
        self.tls_contexts: list[ssl.SSLContext] = []
        self.requests: list[tuple[str, dict[str, str], dict[str, object]]] = []
        self.response_headers: dict[str, str] = {}
        self.call_response_headers: dict[str, str] = {}
        self.status = 200
        self.call_result: dict[str, object] = {"content": [{"type": "text", "text": "done"}]}
        self.tools: list[dict[str, object]] = [{"name": "lookup", "inputSchema": {"type": "object"}}]
        self.tool_pages: list[list[dict[str, object]]] = []
        self.next_cursor = ""
        self.cursor_sequence: list[str] = []
        self.stream_call = False
        self.close_get = False
        self.session = False
        self.cleanup_status = 200
        self.delay = 0.0
        self.tool_delay = 0.0
        self.raw_body = b""
        self.read_size = 65536

    async def connect_tcp(
        self, host: str, port: int, timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        self.connections.append(host)
        await anyio.sleep(self.delay)
        return ScriptedStream(self)

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)


class ScriptedStream(httpcore2.AsyncNetworkStream):
    def __init__(self, network: ScriptedNetwork) -> None:
        self.network = network
        self.sent = bytearray()
        self.ready = anyio.Event()
        self.reply = b""
        self.streaming = False

    async def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.check_hostname
        self.network.sni.append(str(server_hostname))
        self.network.tls_contexts.append(ssl_context)
        return self

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.sent.extend(buffer)
        if b"\r\n\r\n" not in self.sent or self.ready.is_set():
            return
        header_bytes, body = bytes(self.sent).split(b"\r\n\r\n", 1)
        lines = header_bytes.decode().split("\r\n")
        headers = dict(line.lower().split(": ", 1) for line in lines[1:])
        if len(body) < int(headers.get("content-length", "0")):
            return
        message = json.loads(body) if body else {}
        method = lines[0].split()[0]
        self.network.requests.append((method, headers, message))
        rpc_method = message.get("method", "")
        if rpc_method in {"tools/list", "tools/call"}:
            await anyio.sleep(self.network.tool_delay)
        if rpc_method == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "fixture", "version": "1"}}
        elif rpc_method == "tools/list":
            result = {"tools": self.network.tool_pages.pop(0) if self.network.tool_pages else self.network.tools}
            cursor = self.network.cursor_sequence.pop(0) if self.network.cursor_sequence else self.network.next_cursor
            if cursor:
                result["nextCursor"] = cursor
        else:
            result = self.network.call_result
        payload = json.dumps({"jsonrpc": "2.0", "id": message.get("id", 0), "result": result}).encode()
        status = self.network.status
        response_headers = {"content-type": "application/json", **self.network.response_headers}
        if self.network.session:
            response_headers["mcp-session-id"] = "fixture-session"
        if method == "GET":
            self.streaming = not self.network.close_get
            payload = b""
            response_headers["content-type"] = "text/event-stream"
            response_headers["transfer-encoding"] = "chunked"
        elif rpc_method == "notifications/initialized" or method == "DELETE":
            status = self.network.cleanup_status if method == "DELETE" else 202
            payload = b""
        elif rpc_method == "tools/call" and self.network.stream_call:
            payload = b"id: resume-secret\nretry: 0\ndata: \n\n"
            response_headers["content-type"] = "text/event-stream"
        if rpc_method == "tools/call":
            response_headers.update(self.network.call_response_headers)
            if self.network.raw_body:
                payload = self.network.raw_body
        if not self.streaming:
            response_headers.setdefault("content-length", str(len(payload)))
        self.reply = f"HTTP/1.1 {status} Fixture\r\n".encode() + b"".join(f"{key}: {value}\r\n".encode() for key, value in response_headers.items()) + b"\r\n" + payload
        self.ready.set()

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        await self.ready.wait()
        if self.reply:
            size = min(max_bytes, self.network.read_size)
            result, self.reply = self.reply[:size], self.reply[size:]
            return result
        if self.streaming:
            await anyio.sleep_forever()
        return b""

    async def aclose(self) -> None:
        return None


def make_transport(limits: PersonalRuntimeLimits, network: ScriptedNetwork, resolver: ScriptedResolver) -> PersonalMcpTransport:
    return FastMCPPersonalMcpTransport(limits, lambda: datetime.now(timezone.utc), resolver, lambda: network, ssl.create_default_context())


@pytest.fixture
def target() -> PersonalRuntimeTarget:
    return PersonalRuntimeTarget(
        key=PersonalConnectionKey(principal=CanonicalPrincipal(namespace="test", subject="alice"), connector_id="connector"),
        authorization_revision="auth-1", configuration_revision="config-1",
        endpoint_url="https://public.example/mcp?resource=exact", access_token=SecretStr("alice-secret-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


@pytest.fixture
def limits() -> PersonalRuntimeLimits:
    return PersonalRuntimeLimits(
        operation_timeout_seconds=3, maximum_response_bytes=65536,
        maximum_total_bytes=262144, maximum_request_bytes=65536, maximum_tool_pages=3,
    )


@pytest.fixture
def network() -> ScriptedNetwork:
    return ScriptedNetwork()
