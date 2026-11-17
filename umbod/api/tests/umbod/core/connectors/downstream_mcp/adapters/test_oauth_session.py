import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import cast

import httpx2
import pytest
from fastmcp import Client
from mcp.client.auth import AuthorizationCodeResult

from tests.umbod.core.connectors.downstream_mcp.adapters.test_oauth_service import (
    MemoryHost,
)
from umbod.core.connectors.downstream_mcp.adapters import oauth_composition
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_session import (
    FastMCPOAuthSession,
    FastMCPOAuthSessionFactory,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage import (
    AuthorizationDocument,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage_adapters import (
    DetachedConnectorOAuthStorage,
)
from umbod.core.connectors.downstream_mcp.oauth.ports import AuthorizationBeginOptions
from umbod.core.connectors.downstream_mcp.oauth.provider import (
    CLIENT_METADATA_URL,
    InteractiveConnectorOAuth,
)

pytestmark = pytest.mark.asyncio


class RecordingClientContext:
    def __init__(self, suppression: bool | None) -> None:
        self.suppression = suppression
        self.exits: list[
            tuple[type[BaseException] | None, BaseException | None, TracebackType | None]
        ] = []

    async def __aenter__(self) -> Client:
        return Client("https://tools.example/mcp")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        self.exits.append((exc_type, exc, traceback))
        return self.suppression


def recording_session(context: RecordingClientContext) -> FastMCPOAuthSession:
    storage = DetachedConnectorOAuthStorage(
        AuthorizationDocument(endpoint_url="https://tools.example/mcp"), "fixture"
    )
    return FastMCPOAuthSession(InteractiveConnectorOAuth(storage), context)


@pytest.mark.parametrize("suppression", [True, False, None])
async def test_exit_forwards_exact_exception_and_preserves_suppression(
    suppression: bool | None,
) -> None:
    context = RecordingClientContext(suppression)
    session = recording_session(context)
    await session.__aenter__()
    try:
        raise ValueError("session failure")
    except ValueError as error:
        traceback = error.__traceback__
        assert traceback is not None
        result = await session.__aexit__(type(error), error, traceback)
        assert len(context.exits) == 1
        forwarded_type, forwarded_error, forwarded_traceback = context.exits[0]
        assert forwarded_type is type(error)
        assert forwarded_error is error
        assert forwarded_traceback is traceback
    assert result is suppression


@pytest.mark.parametrize("suppression", [True, False, None])
async def test_normal_exit_forwards_no_exception_and_preserves_suppression(
    suppression: bool | None,
) -> None:
    context = RecordingClientContext(suppression)
    session = recording_session(context)
    await session.__aenter__()
    result = await session.__aexit__(None, None, None)
    assert context.exits == [(None, None, None)]
    assert result is suppression


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
