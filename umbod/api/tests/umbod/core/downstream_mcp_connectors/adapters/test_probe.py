from types import SimpleNamespace
from typing import cast

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


class RedirectingClient:
    def __init__(self, location: str | None) -> None:
        self._location = location
        self.server_capabilities = SimpleNamespace(tools=None, prompts=None, resources=None)
        self.server_info = None

    async def __aenter__(self) -> "RedirectingClient":
        if self._location is not None:
            response = _redirect_response(self._location)
            raise httpx2.HTTPStatusError(
                "redirect", request=response.request, response=response
            )
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class RedirectingStrategy:
    def __init__(self, configuration: DownstreamMcpConnectionConfiguration) -> None:
        self._configuration = configuration

    @property
    def configuration(self) -> DownstreamMcpConnectionConfiguration:
        return self._configuration

    def create_client(self) -> Client:
        location = (
            "https://example.com/mcp/"
            if not str(self.configuration.endpoint_url).endswith("/")
            else None
        )
        return cast(Client, RedirectingClient(location))

    def export_authorization(self, client: Client) -> SecretStr | None:
        return None


class RedirectingFactory:
    def __init__(self) -> None:
        self.configurations: list[DownstreamMcpConnectionConfiguration] = []

    def create(
        self, configuration: DownstreamMcpConnectionConfiguration
    ) -> FastMCPConnectionStrategy:
        self.configurations.append(configuration)
        return RedirectingStrategy(configuration)


def _redirect_response(location: str) -> httpx2.Response:
    request = httpx2.Request("POST", "https://example.com/mcp")
    return httpx2.Response(307, headers={"location": location}, request=request)


def test_safe_redirect_accepts_same_origin_https_trailing_slash() -> None:
    response = _redirect_response("https://example.com/mcp/")

    result = FastMCPDownstreamConnection._safe_redirect_url("https://example.com/mcp", response)

    assert result == "https://example.com/mcp/"


def test_safe_redirect_rejects_cross_origin_before_retry() -> None:
    response = _redirect_response("https://other.example/mcp/")

    result = FastMCPDownstreamConnection._safe_redirect_url("https://example.com/mcp", response)

    assert result is None


def test_safe_redirect_accepts_same_origin_loopback_http() -> None:
    response = _redirect_response("http://localhost:8000/mcp/")

    result = FastMCPDownstreamConnection._safe_redirect_url("http://localhost:8000/mcp", response)

    assert result == "http://localhost:8000/mcp/"


def test_safe_redirect_rejects_malformed_location_port() -> None:
    response = _redirect_response("https://example.com:invalid/mcp/")

    result = FastMCPDownstreamConnection._safe_redirect_url("https://example.com/mcp", response)

    assert result is None


def test_safe_redirect_rewrites_proxy_trailing_slash_downgrade_to_https() -> None:
    response = _redirect_response("http://example.com/mcp/")

    result = FastMCPDownstreamConnection._safe_redirect_url("https://example.com/mcp", response)

    assert result == "https://example.com/mcp/"


def test_safe_redirect_rejects_genuine_https_downgrade() -> None:
    response = _redirect_response("http://example.com/other")

    result = FastMCPDownstreamConnection._safe_redirect_url("https://example.com/mcp", response)

    assert result is None


def test_safe_redirect_rejects_proxy_rewrite_when_query_changes() -> None:
    response = _redirect_response("http://example.com/mcp/?page=2")

    result = FastMCPDownstreamConnection._safe_redirect_url(
        "https://example.com/mcp?page=1", response
    )

    assert result is None


@pytest.mark.asyncio
async def test_public_probe_recreates_strategy_for_safe_redirect() -> None:
    factory = RedirectingFactory()
    probe = FastMCPDownstreamConnection(True, 1, factory)

    result = await probe.probe(
        NoAuthConnectionConfiguration(endpoint_url="https://example.com/mcp")
    )

    assert isinstance(result, ProbeCapabilities)
    assert str(result.endpoint_url) == "https://example.com/mcp/"
    assert [str(item.endpoint_url) for item in factory.configurations] == [
        "https://example.com/mcp",
        "https://example.com/mcp/",
    ]


def test_exception_classification_terminates_for_cyclic_exception_chain() -> None:
    connection = FastMCPDownstreamConnection(
        tls_verification=True,
        timeout_seconds=1,
        connection_factory=FastMCPDownstreamConnectionFactory(True),
    )
    outer_error = RuntimeError("outer")
    transport_error = httpx2.ConnectError("connection failed")
    outer_error.__cause__ = transport_error
    transport_error.__context__ = outer_error

    result = connection._classify_exception(outer_error)

    assert result == ProbeFailed(code="unreachable")
