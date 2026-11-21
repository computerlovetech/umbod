from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from pydantic import TypeAdapter, ValidationError

from umbod.core.mcp_registry.models import RegistryEndpointUrl

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
    HttpRequestError,
    JsonHttpLimits,
    OutboundHttpClientFactory,
)

from .schemas import RegistryListing, RegistryRemote, RegistrySearchResponse

OFFICIAL_REGISTRY_ORIGIN = "https://registry.modelcontextprotocol.io"
_ICON_URL = TypeAdapter(RegistryEndpointUrl)


class OfficialMcpRegistry:
    def __init__(self, client: AsyncJsonHttpClient) -> None:
        self._client = client

    async def search(self, query: RegistrySearch) -> RegistryPage:
        params: dict[str, str | int] = {
            "search": query.term,
            "version": "latest",
            "limit": query.limit,
        }
        if query.cursor:
            params["cursor"] = query.cursor
        try:
            body = await self._client.get_json("/v0.1/servers", params=params)
            return _to_page(RegistrySearchResponse.model_validate_json(body))
        except HttpRequestError, ValidationError:
            pass
        raise RegistryUnavailableError("Official MCP registry is unavailable")


@asynccontextmanager
async def open_official_mcp_registry() -> AsyncIterator[McpRegistry]:
    factory = OutboundHttpClientFactory(3.0, 5.0, 5.0, 3.0)
    async with factory.create_for_origin(OFFICIAL_REGISTRY_ORIGIN) as client:
        yield OfficialMcpRegistry(AsyncJsonHttpClient(client, limits=JsonHttpLimits()))


def _to_page(response: RegistrySearchResponse) -> RegistryPage:
    servers = []
    for listing in response.servers:
        server = _compatible_server(listing)
        if server is not None:
            servers.append(server)
    return RegistryPage(
        servers=tuple(servers), next_cursor=response.metadata.next_cursor
    )


def _compatible_server(listing: RegistryListing) -> RegistryServer | None:
    official = listing.metadata.official
    if official.status != "active":
        return None
    server = listing.server
    endpoints = tuple(dict.fromkeys(_compatible_endpoints(server.remotes)))
    if not endpoints:
        return None
    return RegistryServer(
        name=server.name,
        title=server.title.strip() or server.name,
        description=server.description,
        version=server.version,
        icons=tuple(dict.fromkeys(_compatible_icons(server.icons)))[:4],
        endpoints=endpoints,
    )


def _compatible_icons(icons: Iterable[object]) -> Iterable[str]:
    for icon in icons:
        if not isinstance(icon, dict) or not isinstance(icon.get("src"), str):
            continue
        try:
            yield _ICON_URL.validate_python(icon["src"])
        except ValidationError:
            continue


def _compatible_endpoints(
    remotes: Iterable[RegistryRemote],
) -> Iterable[RegistryEndpoint]:
    for remote in remotes:
        if remote.type != "streamable-http":
            continue
        try:
            endpoint = RegistryEndpoint(
                url=remote.url,
                required_headers=tuple(
                    sorted(
                        {
                            header.name.strip().lower()
                            for header in remote.headers
                            if header.required and header.name.strip()
                        }
                    )
                ),
            )
        except ValidationError:
            continue
        yield endpoint
