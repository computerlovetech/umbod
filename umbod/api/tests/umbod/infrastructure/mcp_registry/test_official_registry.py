from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest

from umbod.core.mcp_registry import (
    McpRegistry,
    RegistryEndpoint,
    RegistryPage,
    RegistrySearch,
    RegistryServer,
    RegistryUnavailableError,
)
from umbod.infrastructure.http import (
    AsyncJsonHttpClient,
    JsonHttpLimits,
    OutboundHttpClientFactory,
)
from umbod.infrastructure.http.httpx_client import HttpxClientProxy
from umbod.infrastructure.mcp_registry import (
    OFFICIAL_REGISTRY_ORIGIN,
    OfficialMcpRegistry,
    open_official_mcp_registry,
)


_QUERY = RegistrySearch(term="catalog & tools", limit=7)
_ENDPOINT = "https://primary.example.test/mcp"
_MIRROR = "https://mirror.example.test/mcp"
_OFFICIAL_METADATA = "io.modelcontextprotocol.registry/official"


def _listing(
    name: str, *, status: str = "active", **server_fields: object
) -> dict[str, object]:
    return {
        "server": {
            "name": name,
            "description": "Catalog tools",
            "version": "1.2",
            **server_fields,
        },
        "_meta": {_OFFICIAL_METADATA: {"status": status}},
    }


def _remote(
    url: str, kind: str = "streamable-http", **fields: object
) -> dict[str, object]:
    return {"type": kind, "url": url, **fields}


def _http_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=OFFICIAL_REGISTRY_ORIGIN, transport=httpx.MockTransport(handler)
    )


@asynccontextmanager
async def _registry(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AsyncIterator[McpRegistry]:
    async with _http_client(handler) as client:
        yield OfficialMcpRegistry(AsyncJsonHttpClient(HttpxClientProxy(client), limits=JsonHttpLimits()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor", ["", "page/+&=2"], ids=["first-page", "continuation"]
)
async def test_search_sends_only_the_official_list_request(cursor: str) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"servers": [], "metadata": {"count": 0}})

    async with _registry(respond) as registry:
        await registry.search(
            RegistrySearch(term=_QUERY.term, limit=_QUERY.limit, cursor=cursor)
        )

    (request,) = requests
    assert request.method == "GET"
    assert request.url.copy_with(query=None) == httpx.URL(
        "https://registry.modelcontextprotocol.io/v0.1/servers"
    )
    params = [("limit", "7"), ("search", "catalog & tools"), ("version", "latest")]
    if cursor:
        params.append(("cursor", cursor))
    assert sorted(request.url.params.multi_items()) == sorted(params)


@pytest.mark.asyncio
async def test_search_maps_only_active_official_listings_with_concrete_https_remotes() -> (
    None
):
    listings = [
        _listing(
            "example/catalog",
            title="Catalog",
            icons=[{"src": "https://primary.example.test/logo.png"}, {"src": "http://insecure.example.test/logo.png"}, None, {"src": 7}, {"src": "https://primary.example.test/logo.png"}],
            remotes=[
                _remote(
                    _ENDPOINT,
                    headers=[
                        {
                            "name": "Authorization",
                            "value": "Bearer private",
                            "isRequired": True,
                        }
                    ],
                ),
                _remote(_MIRROR),
                _remote(_MIRROR),
                {"type": "streamable-http"},
                _remote("https://legacy.example.test/sse", "sse"),
                _remote("http://insecure.example.test/mcp"),
                _remote("https:///no-host"),
                _remote("https://{tenant}.example.test/mcp"),
                _remote("https://primary.example.test/{tenant}/mcp"),
                _remote("https://user:private@primary.example.test/mcp"),
                _remote("https://primary.example.test/mcp?region=example"),
            ],
        ),
        _listing("example/second", title=None, remotes=[_remote(_MIRROR)]),
        _listing(
            "example/deprecated", status="deprecated", remotes=[_remote(_ENDPOINT)]
        ),
        {
            **_listing("example/unofficial", remotes=[_remote(_ENDPOINT)]),
            "_meta": {"other": {}},
        },
        _listing(
            "example/package", packages=[{"registryType": "npm", "identifier": "tools"}]
        ),
        _listing("example/no-remotes", remotes=None),
        {
            **_listing("example/no-metadata", remotes=[_remote(_ENDPOINT)]),
            "_meta": None,
        },
        {
            **_listing("example/no-official-metadata", remotes=[_remote(_ENDPOINT)]),
            "_meta": {_OFFICIAL_METADATA: None},
        },
        _listing("example/sse", remotes=[_remote(_ENDPOINT, "sse")]),
    ]
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "servers": listings,
                "metadata": {"count": len(listings), "nextCursor": None},
            },
        )

    async with _registry(respond) as registry:
        page = await registry.search(_QUERY)

    assert page == RegistryPage(
        servers=(
            RegistryServer(
                name="example/catalog",
                title="Catalog",
                description="Catalog tools",
                version="1.2",
                icons=("https://primary.example.test/logo.png",),
                endpoints=(
                    RegistryEndpoint(
                        url=_ENDPOINT, required_headers=("authorization",)
                    ),
                    RegistryEndpoint(url=_MIRROR, required_headers=()),
                ),
            ),
            RegistryServer(
                name="example/second",
                title="example/second",
                description="Catalog tools",
                version="1.2",
                endpoints=(RegistryEndpoint(url=_MIRROR, required_headers=()),),
            ),
        ),
        next_cursor="",
    )
    assert [request.url.host for request in requests] == [
        "registry.modelcontextprotocol.io"
    ]


@pytest.mark.asyncio
async def test_search_preserves_cursor_when_every_listing_is_filtered() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "servers": [
                    _listing(
                        "example/template", remotes=[_remote("https://{host}/mcp")]
                    )
                ],
                "metadata": {"count": 1, "nextCursor": "original/+&=cursor"},
            },
        )

    async with _registry(respond) as registry:
        page = await registry.search(_QUERY)

    assert page == RegistryPage(servers=(), next_cursor="original/+&=cursor")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body"),
    [
        (503, b"private upstream error"),
        (200, b"private invalid JSON"),
        (200, b'{"servers":"private invalid field","metadata":{}}'),
        (200, b'{"servers":[],"metadata":{"nextCursor":{"private":"invalid"}}}'),
    ],
    ids=["upstream-status", "malformed-json", "invalid-listings", "invalid-cursor"],
)
async def test_search_normalizes_provider_response_errors(
    status: int, body: bytes
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    async with _registry(respond) as registry:
        with pytest.raises(
            RegistryUnavailableError, match="^Official MCP registry is unavailable$"
        ) as error:
            await registry.search(_QUERY)

    assert error.value.__context__ is None


@pytest.mark.asyncio
async def test_search_normalizes_transport_failures() -> None:
    def disconnect(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private network details", request=request)

    async with _registry(disconnect) as registry:
        with pytest.raises(
            RegistryUnavailableError, match="^Official MCP registry is unavailable$"
        ):
            await registry.search(_QUERY)


@pytest.mark.asyncio
async def test_open_official_registry_sets_origin_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"servers": [], "metadata": {}})

    client = _http_client(respond)
    origins: list[str] = []

    def create_for_origin(
        factory: OutboundHttpClientFactory, base_url: str
    ) -> HttpxClientProxy:
        origins.append(base_url)
        return HttpxClientProxy(client)

    monkeypatch.setattr(
        OutboundHttpClientFactory, "create_for_origin", create_for_origin
    )
    async with open_official_mcp_registry() as registry:
        assert await registry.search(_QUERY) == RegistryPage(servers=(), next_cursor="")

    assert origins == ["https://registry.modelcontextprotocol.io"]
    assert client.is_closed
