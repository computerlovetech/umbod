import pytest
from pydantic import ValidationError

from umbod.core.mcp_registry import (
    McpRegistry,
    RegistryEndpoint,
    RegistryPage,
    RegistrySearch,
    RegistryServer,
)


class InMemoryRegistry:
    def __init__(self, servers: tuple[RegistryServer, ...]) -> None:
        self._servers = servers

    async def search(self, query: RegistrySearch) -> RegistryPage:
        matches = tuple(server for server in self._servers if query.term in server.name)
        offset = int(query.cursor or "0")
        stop = offset + query.limit
        return RegistryPage(
            servers=matches[offset:stop],
            next_cursor=str(stop) if stop < len(matches) else "",
        )


@pytest.mark.asyncio
async def test_registry_callers_can_continue_using_the_returned_cursor() -> None:
    servers = tuple(
        RegistryServer(
            name=f"example.com/demo-{index}",
            title=f"Demo {index}",
            description="",
            version="1.0.0",
            endpoints=(
                RegistryEndpoint(
                    url=f"https://example.com/mcp/{index}", required_headers=()
                ),
            ),
        )
        for index in range(2)
    )
    registry: McpRegistry = InMemoryRegistry(servers)
    first = await registry.search(RegistrySearch(term="  demo  ", limit=1))
    final = await registry.search(
        RegistrySearch(term="demo", limit=1, cursor=first.next_cursor)
    )
    assert first.servers + final.servers == servers
    assert final.next_cursor == ""


@pytest.mark.parametrize(("term", "limit"), [(" sh ", 20), ("demo", 0), ("demo", 101)])
def test_registry_search_rejects_invalid_criteria(term: str, limit: int) -> None:
    with pytest.raises(ValidationError):
        RegistrySearch(term=term, limit=limit)
