import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import httpx2
import pytest
from fastmcp import Client
from mcp.client.auth import AuthorizationCodeResult

from tests.umbod.core.downstream_mcp_connectors.adapters.test_oauth_service import (
    MemoryHost,
)
from umbod.core.connectors.downstream_mcp.adapters import oauth_composition
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_session import (
    FastMCPOAuthSessionFactory,
)
from umbod.core.connectors.downstream_mcp.oauth.ports import AuthorizationBeginOptions
from umbod.core.connectors.downstream_mcp.oauth.provider import (
    CLIENT_METADATA_URL,
    InteractiveConnectorOAuth,
)

pytestmark = pytest.mark.asyncio


class ToolClient:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.discoveries = 0

    async def list_tools(self) -> list[object]:
        self.discoveries += 1
        if self.failure == "discovery":
            raise ValueError("discovery failed")
        if self.failure == "cancel":
            raise asyncio.CancelledError
        return []


@pytest.mark.parametrize("failure", ["", "enter", "discovery", "cancel"])
async def test_session_delegates_token_state_and_disposes_transport(
    failure: str,
) -> None:
    host = MemoryHost()
    clients: list[ToolClient] = []
    disposed: list[str] = []
    authorizations: list[InteractiveConnectorOAuth] = []

    @asynccontextmanager
    async def client_factory(
        endpoint_url: str, auth: InteractiveConnectorOAuth
    ) -> AsyncIterator[Client]:
        authorizations.append(auth)
        client = ToolClient(failure)
        clients.append(client)
        try:
            auth.token_received = True
            if failure == "enter":
                raise ValueError("enter failed")
            yield cast(Client, client)
        finally:
            disposed.append(endpoint_url)

    async def redirect_handler(url: str) -> None:
        return None

    async def callback_handler() -> AuthorizationCodeResult:
        return AuthorizationCodeResult(code="code", state="state")

    factory = FastMCPOAuthSessionFactory(client_factory)
    session = factory.begin(
        host.saved,
        AuthorizationBeginOptions(
            endpoint="https://tools.example/mcp",
            requested_scopes="read write",
            metadata_mode="hosted_metadata",
            redirect_uri="http://127.0.0.1/callback",
        ),
        redirect_handler,
        callback_handler,
    )
    assert not session.token_received
    if failure:
        with pytest.raises(
            asyncio.CancelledError if failure == "cancel" else ValueError
        ):
            async with session:
                await session.discover_tools()
    else:
        async with session:
            await session.discover_tools()
    assert session.token_received
    assert disposed == ["https://tools.example/mcp"]
    assert authorizations[0].requested_scope == "read write"
    assert authorizations[0].context.client_metadata_url == CLIENT_METADATA_URL
    assert authorizations[0].force_authorization
    if not failure:
        refresh = factory.refresh(host.saved)
        async with refresh:
            pass
        assert authorizations[1] is not authorizations[0]
        assert authorizations[1].force_refresh
        assert not authorizations[1].force_authorization


async def test_composition_discovers_with_owned_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients: list[httpx2.AsyncClient] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404)

    def create_client() -> httpx2.AsyncClient:
        client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(handle), timeout=8, follow_redirects=False
        )
        clients.append(client)
        return client

    monkeypatch.setattr(oauth_composition, "create_metadata_client", create_client)
    service = oauth_composition.create_oauth_service(MemoryHost())
    try:
        preview = await service.discover("fixture")
        assert preview["registration"] == "unknown"
        assert preview["canonical_endpoint"] == "https://tools.example/mcp"
        assert clients[0].is_closed
        await service.discover("fixture")
        assert len(clients) == 2
        assert clients[1].is_closed
    finally:
        await service.close()
