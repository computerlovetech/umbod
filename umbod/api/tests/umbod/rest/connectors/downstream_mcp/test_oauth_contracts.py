from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from mcp.shared.auth import OAuthToken

from tests.persistence_runtime import create_inmemory_runtime
from tests.umbod.core.connectors.downstream_mcp.adapters.oauth_fakes import (
    MemoryDiscovery,
    ScriptedSessionFactory,
)
from tests.umbod.core.connectors.downstream_mcp.adapters.test_oauth_service import MemoryHost
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_DEFINITION_TABLE,
    ConnectorDefinitionStore,
    ConnectorDefinitionStoreService,
)
from umbod.rest.connectors.downstream_mcp.dependencies import get_definition_store
from umbod.rest.connectors.downstream_mcp.oauth import get_oauth_service, router

pytestmark = pytest.mark.asyncio
OAUTH_URL = "/connectors/mcp/oauth/fixture"


@pytest_asyncio.fixture
async def oauth_service() -> AsyncIterator[OAuthService]:
    service = OAuthService(MemoryHost(), ScriptedSessionFactory(""), MemoryDiscovery())
    try:
        yield service
    finally:
        await service.close()


@pytest_asyncio.fixture
async def oauth_client(oauth_service: OAuthService) -> AsyncIterator[httpx.AsyncClient]:
    definitions = ConnectorDefinitionStoreService(
        create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE
    )

    def provide_definitions() -> ConnectorDefinitionStore:
        return definitions

    def provide_service() -> OAuthService:
        return oauth_service

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_definition_store] = provide_definitions
    app.dependency_overrides[get_oauth_service] = provide_service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_details_before_discovery_serializes_unknown_endpoint_fields_as_null(
    oauth_client: httpx.AsyncClient,
) -> None:
    response = await oauth_client.get(OAUTH_URL)
    assert response.status_code == 200
    payload = response.json()
    assert payload["canonical_endpoint"] is None
    assert payload["endpoint_differs"] is None
    assert payload["issuer"] is None


async def test_discovered_matching_endpoint_serializes_false_instead_of_null(
    oauth_client: httpx.AsyncClient,
) -> None:
    response = await oauth_client.post(OAUTH_URL + "/discover")
    assert response.status_code == 200
    payload = response.json()
    assert payload["canonical_endpoint"] == "https://tools.example/mcp"
    assert payload["endpoint_differs"] is False
    assert payload["issuer"] == "https://auth.example"
    details = await oauth_client.get(OAUTH_URL)
    assert details.status_code == 200
    assert details.json()["endpoint_differs"] is False


@pytest.mark.parametrize("granted_scopes", [None, ""])
async def test_details_preserves_unknown_and_empty_granted_scopes(
    oauth_client: httpx.AsyncClient,
    oauth_service: OAuthService,
    granted_scopes: str | None,
) -> None:
    await oauth_service.host.storage("fixture").set_tokens(
        OAuthToken(access_token="saved", token_type="Bearer", scope=granted_scopes)
    )
    response = await oauth_client.get(OAUTH_URL)
    assert response.status_code == 200
    assert response.json()["granted_scopes"] == granted_scopes
    assert response.json()["has_authorization"] is True


@pytest.mark.parametrize("error", [None, "Browser sign-in timed out. Return to Connection settings and try again."])
async def test_details_preserves_null_and_fixed_failure_error(
    oauth_client: httpx.AsyncClient,
    oauth_service: OAuthService,
    error: str | None,
) -> None:
    if error is not None:
        oauth_service.errors["fixture"] = error
    response = await oauth_client.get(OAUTH_URL)
    assert response.status_code == 200
    assert response.json()["error"] == error
