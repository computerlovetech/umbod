from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast

from fastmcp.client.transports import StreamableHttpTransport

import httpx2
import pytest
from fastmcp import Client
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.connection import (
    DownstreamMcpConnectionConfiguration,
    NoAuthConnectionConfiguration,
)
from umbod.core.connectors.downstream_mcp.probe import ProbeCapabilities, ProbeFailed
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import (
    FastMCPConnectionStrategy,
    FastMCPDownstreamConnectionFactory,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.probe import FastMCPDownstreamConnection


class ProbeClient:
    def __init__(self, error: Exception | None) -> None:
        self.error = error
        self.server_capabilities = SimpleNamespace(tools=None, prompts=None, resources=None)
        self.server_info = None

    async def __aenter__(self) -> "ProbeClient":
        if self.error is not None:
            raise self.error
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class ProbeStrategy:
    def __init__(
        self, configuration: DownstreamMcpConnectionConfiguration, error: Exception | None
    ) -> None:
        self.configuration = configuration
        self.error = error

    def create_client(self) -> Client:
        return cast(Client, ProbeClient(self.error))

    def export_authorization(self, client: Client) -> SecretStr | None:
        return None


class ProbeFactory:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.configurations: list[DownstreamMcpConnectionConfiguration] = []

    def create(
        self, configuration: DownstreamMcpConnectionConfiguration
    ) -> FastMCPConnectionStrategy:
        self.configurations.append(configuration)
        error = self.error if len(self.configurations) == 1 else None
        return ProbeStrategy(configuration, error)


def redirect_factory(endpoint: str, location: str) -> ProbeFactory:
    request = httpx2.Request("POST", endpoint)
    response = httpx2.Response(307, headers={"location": location}, request=request)
    return ProbeFactory(
        httpx2.HTTPStatusError("redirect", request=request, response=response)
    )


@pytest.mark.asyncio
async def test_safe_redirect_accepts_same_origin_https_trailing_slash() -> None:
    factory = redirect_factory("https://example.com/mcp", "https://example.com/mcp/")
    result = await FastMCPDownstreamConnection(True, 1, factory).probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp")
    )

    assert isinstance(result, ProbeCapabilities)
    assert str(result.endpoint_url) == "https://example.com/mcp/"
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "https://example.com/mcp", "https://example.com/mcp/"
    ]


@pytest.mark.asyncio
async def test_safe_redirect_rejects_cross_origin_before_retry() -> None:
    factory = redirect_factory("https://example.com/mcp", "https://other.example/mcp/")
    result = await FastMCPDownstreamConnection(True, 1, factory).probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp")
    )

    assert result == ProbeFailed(code="unsafe_redirect")
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "https://example.com/mcp"
    ]


@pytest.mark.asyncio
async def test_safe_redirect_accepts_same_origin_loopback_http() -> None:
    factory = redirect_factory("http://localhost:8000/mcp", "http://localhost:8000/mcp/")
    result = await FastMCPDownstreamConnection(True, 1, factory).probe(
        NoAuthConnectionConfiguration(endpoint_url="http://localhost:8000/mcp")
    )

    assert isinstance(result, ProbeCapabilities)
    assert str(result.endpoint_url) == "http://localhost:8000/mcp/"
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "http://localhost:8000/mcp", "http://localhost:8000/mcp/"
    ]


@pytest.mark.asyncio
async def test_safe_redirect_rejects_malformed_location_port() -> None:
    factory = redirect_factory("https://example.com/mcp", "https://example.com:invalid/mcp/")
    result = await FastMCPDownstreamConnection(True, 1, factory).probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp")
    )

    assert result == ProbeFailed(code="unsafe_redirect")
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "https://example.com/mcp"
    ]


@pytest.mark.asyncio
async def test_safe_redirect_rewrites_proxy_trailing_slash_downgrade_to_https() -> None:
    factory = redirect_factory("https://example.com/mcp", "http://example.com/mcp/")
    result = await FastMCPDownstreamConnection(True, 1, factory).probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp")
    )

    assert isinstance(result, ProbeCapabilities)
    assert str(result.endpoint_url) == "https://example.com/mcp/"
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "https://example.com/mcp", "https://example.com/mcp/"
    ]


@pytest.mark.asyncio
async def test_safe_redirect_rejects_genuine_https_downgrade() -> None:
    factory = redirect_factory("https://example.com/mcp", "http://example.com/other")
    result = await FastMCPDownstreamConnection(True, 1, factory).probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp")
    )

    assert result == ProbeFailed(code="unsafe_redirect")
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "https://example.com/mcp"
    ]


@pytest.mark.asyncio
async def test_safe_redirect_rejects_proxy_rewrite_when_query_changes() -> None:
    factory = redirect_factory(
        "https://example.com/mcp?page=1", "http://example.com/mcp/?page=2"
    )
    result = await FastMCPDownstreamConnection(True, 1, factory).probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp?page=1")
    )

    assert result == ProbeFailed(code="unsafe_redirect")
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "https://example.com/mcp?page=1"
    ]


@pytest.mark.asyncio
async def test_exception_classification_terminates_for_cyclic_exception_chain() -> None:
    outer_error = RuntimeError("outer")
    transport_error = httpx2.ConnectError("connection failed")
    outer_error.__cause__ = transport_error
    transport_error.__context__ = outer_error
    connection = FastMCPDownstreamConnection(True, 1, ProbeFactory(outer_error))

    result = await connection.probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp")
    )

    assert result == ProbeFailed(code="unreachable")


@pytest.mark.asyncio
async def test_probe_transport_extends_httpx_default_read_timeout() -> None:
    strategy = FastMCPDownstreamConnectionFactory(True, None, oauth_enabled=False).create(
        NoAuthConnectionConfiguration(endpoint_url="http://127.0.0.1:8000/mcp")
    )
    transport = strategy.create_client().transport
    assert isinstance(transport, StreamableHttpTransport)
    assert transport.httpx_client_factory is not None

    async with transport.httpx_client_factory() as client:
        assert client.timeout == httpx2.Timeout(30.0, read=300.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("deadline, succeeds", [(2.0, True), (0.1, False)])
async def test_catalog_respects_probe_deadline(deadline: float, succeeds: bool) -> None:
    import asyncio
    import socket

    import uvicorn
    from fastmcp import FastMCP
    from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
    from mcp.types import ListToolsRequest
    from fastmcp.tools import Tool

    class SlowCatalog(Middleware):
        async def on_list_tools(
            self,
            context: MiddlewareContext[ListToolsRequest],
            call_next: CallNext[ListToolsRequest, Sequence[Tool]],
        ) -> Sequence[Tool]:
            await asyncio.sleep(0.3)
            return await call_next(context)

    fixture = FastMCP("slow-catalog", middleware=[SlowCatalog()])

    @fixture.tool
    def echo(text: str) -> str:
        return text

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        endpoint = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
        server = uvicorn.Server(uvicorn.Config(fixture.http_app(path="/mcp"), log_level="error"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.01)
            probe = FastMCPDownstreamConnection(True, deadline, FastMCPDownstreamConnectionFactory(True, None, oauth_enabled=False))
            result = await probe.probe(NoAuthConnectionConfiguration(endpoint_url=endpoint))
            if succeeds:
                assert isinstance(result, ProbeCapabilities)
                assert [tool.name for tool in result.capabilities.tools] == ["echo"]
            else:
                assert result == ProbeFailed(code="timeout")
        finally:
            server.should_exit = True
            await task
