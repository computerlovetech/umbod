import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.core.mcp_registry import (
    McpRegistry,
    RegistryEndpoint,
    RegistryPage,
    RegistrySearch,
    RegistryServer,
    RegistryUnavailableError,
)
from umbod.rest.connectors.downstream_mcp import registry
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings

_SEARCH_PATH = "/api/admin/connectors/mcp/registry/search"
_CURSOR = "opaque+cursor/="


class InMemoryRegistry:
    def __init__(self) -> None:
        self.queries: list[RegistrySearch] = []
        self.page = RegistryPage(servers=(), next_cursor="")
        self.unavailable = False
        self.active = False
        self.open_count = 0

    @asynccontextmanager
    async def open(self) -> AsyncIterator[McpRegistry]:
        self.open_count += 1
        self.active = True
        try:
            yield self
        finally:
            self.active = False

    async def search(self, query: RegistrySearch) -> RegistryPage:
        if not self.active:
            raise RuntimeError("Registry is not open")
        self.queries.append(query)
        if self.unavailable:
            raise RegistryUnavailableError("Provider payload: private data")
        return self.page


@pytest.fixture
def registry_provider(monkeypatch: pytest.MonkeyPatch) -> InMemoryRegistry:
    provider = InMemoryRegistry()
    monkeypatch.setattr(registry, "open_official_mcp_registry", provider.open)
    return provider


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    availability = tmp_path / "availability.json"
    availability.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability)
    )
    settings = APISettings(
        connector_store={"type": "inmemory"},
        rest={"metrics_enabled": False},
        admin_authentication={
            "mode": "jwt",
            "environment": "development",
            "jwt_header_name": "Authorization",
        },
    )
    with TestClient(create_app(settings, [])) as transport:
        yield transport


def _membership_headers(group: str) -> dict[str, str]:
    token = json.dumps({"signature": "trusted", "claims": {"groups": [group]}})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return _membership_headers("umbod-admins")


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [({}, 401), (_membership_headers("umbod-users"), 403)],
)
def test_registry_search_requires_admin_before_opening_provider(
    client: TestClient,
    registry_provider: InMemoryRegistry,
    headers: dict[str, str],
    expected_status: int,
) -> None:
    response = client.get(_SEARCH_PATH, params={"term": "demo"}, headers=headers)

    assert response.status_code == expected_status
    assert registry_provider.open_count == 0


def test_registry_search_returns_listings_and_forwards_pagination(
    client: TestClient,
    registry_provider: InMemoryRegistry,
    admin_headers: dict[str, str],
) -> None:
    registry_provider.page = RegistryPage(
        servers=(
            RegistryServer(
                name="example/demo",
                title="Demo",
                description="Demo server",
                version="1.2.3",
                icons=("https://demo.example/logo.png",),
                endpoints=(
                    RegistryEndpoint(
                        url="https://demo.example/mcp",
                        required_headers=("authorization",),
                    ),
                ),
            ),
        ),
        next_cursor="next-page",
    )

    response = client.get(
        _SEARCH_PATH,
        params={"term": "  demo  ", "limit": 7, "cursor": _CURSOR},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "servers": [
            {
                "name": "example/demo",
                "title": "Demo",
                "description": "Demo server",
                "version": "1.2.3",
                "icons": ["https://demo.example/logo.png"],
                "endpoints": [
                    {
                        "url": "https://demo.example/mcp",
                        "required_headers": ["authorization"],
                    }
                ],
            }
        ],
        "next_cursor": "next-page",
    }
    assert registry_provider.queries == [
        RegistrySearch(term="demo", limit=7, cursor=_CURSOR)
    ]
    assert not registry_provider.active


def test_registry_search_returns_empty_page_with_default_pagination(
    client: TestClient,
    registry_provider: InMemoryRegistry,
    admin_headers: dict[str, str],
) -> None:
    response = client.get(_SEARCH_PATH, params={"term": "demo"}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {"servers": [], "next_cursor": ""}
    assert registry_provider.queries == [
        RegistrySearch(term="demo", limit=20, cursor="")
    ]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"term": "  "},
        {"term": "x" * 257},
        {"term": "demo", "limit": "0"},
        {"term": "demo", "limit": "101"},
        {"term": "demo", "cursor": "x" * 2049},
        {"term": "demo", "unknown": "parameter"},
    ],
)
def test_registry_search_rejects_invalid_query_without_searching(
    client: TestClient,
    registry_provider: InMemoryRegistry,
    admin_headers: dict[str, str],
    params: dict[str, str],
) -> None:
    response = client.get(_SEARCH_PATH, params=params, headers=admin_headers)

    assert response.status_code == 422
    assert not registry_provider.queries


def test_registry_search_sanitizes_provider_failure(
    client: TestClient,
    registry_provider: InMemoryRegistry,
    admin_headers: dict[str, str],
) -> None:
    registry_provider.unavailable = True

    response = client.get(_SEARCH_PATH, params={"term": "demo"}, headers=admin_headers)

    assert response.status_code == 502
    assert response.json() == {"detail": {"code": "mcp_registry_unavailable"}}
    assert not registry_provider.active
