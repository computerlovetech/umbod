import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount
from pydantic import SecretStr

from tests.umbod.rest.downstream_mcp_connectors.personal_connections.test_personal_connection_routes import (
    PersonalApi,
    personal_api as personal_api,
)
from tests.umbod.rest.user_catalogue.query_budget_support import QueryCounts
from tests.umbod.rest.user_catalogue.test_catalogue_query_budget import (
    catalogue_http as catalogue_http,
    seed_shared_tools,
)
from umbod.config.defaults import LOCAL_DOWNSTREAM_MCP_CREDENTIAL_SECRET
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey, ReplacePersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import (
    AbsentPersonalRefreshToken, ExpiringPersonalToken, PersonalOAuthGrant, authorize_personal_grant,
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationQuery
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.personal_connections.tools import get_personal_tool_transport
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_verified_access_claims
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.settings import APISettings
from umbod.rest.user_catalogue.dependencies import get_personal_catalogue_store_supplier
from umbod.rest.user_catalogue.ports import PersonalCatalogueStoreSupplier


class FailingPersonalCatalogueStoreSupplier:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.calls = 0

    async def create(self) -> DownstreamMcpStores:
        self.calls += 1
        raise self.failure


class RecordingPersonalCatalogueStoreSupplier:
    def __init__(self, delegate: PersonalCatalogueStoreSupplier, stores: list[DownstreamMcpStores]) -> None:
        self.delegate = delegate
        self.stores = stores

    async def create(self) -> DownstreamMcpStores:
        stores = await self.delegate.create()
        self.stores.append(stores)
        return stores


def mounted_catalogue_app(client: TestClient) -> FastAPI:
    return next(route.app for route in client.app.routes if isinstance(route, Mount) and route.path == "/api/me")


@pytest.mark.parametrize("enabled", [False, True])
def test_ineligible_identity_does_not_create_personal_stores_but_retains_shared_catalogue(
    catalogue_http: tuple[TestClient, ConnectorApiDependencyFactories, QueryCounts], enabled: bool,
) -> None:
    client, factories, _ = catalogue_http
    settings = factories.settings.model_dump()
    settings["personal_connections"]["enabled"] = enabled
    settings["personal_connections"]["identity_namespace"] = "test:supplier-laziness"
    factories.settings = APISettings.model_validate(settings)
    client.portal.call(seed_shared_tools, factories, 1)
    supplier = FailingPersonalCatalogueStoreSupplier(AssertionError("Personal stores must stay lazy"))
    app = mounted_catalogue_app(client)

    def provide_supplier() -> PersonalCatalogueStoreSupplier:
        return supplier

    def unmapped_claims() -> JwtClaims:
        return JwtClaims(claims={"email": "reader@example.test", "groups": ["readers"]})

    app.dependency_overrides[get_personal_catalogue_store_supplier] = provide_supplier
    app.dependency_overrides[get_verified_access_claims] = unmapped_claims
    try:
        response = client.get("/api/me/catalogue")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["personal_enabled"] is enabled
        assert [connector["connector_id"] for connector in response.json()["connectors"]] == ["shared"]
        assert supplier.calls == 0
    finally:
        del app.dependency_overrides[get_personal_catalogue_store_supplier]
        del app.dependency_overrides[get_verified_access_claims]


@pytest.fixture
def recorded_stores(personal_api: PersonalApi) -> Iterator[list[DownstreamMcpStores]]:
    stores: list[DownstreamMcpStores] = []

    def provide_supplier(
        factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    ) -> PersonalCatalogueStoreSupplier:
        return RecordingPersonalCatalogueStoreSupplier(factories.personal_catalogue_stores, stores)

    personal_api.personal_app.dependency_overrides[get_personal_catalogue_store_supplier] = provide_supplier
    try:
        yield stores
    finally:
        del personal_api.personal_app.dependency_overrides[get_personal_catalogue_store_supplier]


def test_resolved_requests_create_fresh_stores_and_recheck_current_groups_and_grants(
    personal_api: PersonalApi, recorded_stores: list[DownstreamMcpStores],
) -> None:
    api = personal_api
    assert api.settings.personal_connections.oauth_enabled is False
    for subject, expected_count in (("alice", 1), ("bob", 1), ("administrator", 0)):
        response = api.client.get("/api/me/catalogue", headers=api.headers(subject))
        assert response.status_code == 200
        assert len(response.json()["connectors"]) == expected_count
    assert len(recorded_stores) == 3
    assert recorded_stores[0] is not recorded_stores[1]
    assert recorded_stores[0].personal_connections is not recorded_stores[1].personal_connections
    api.client.portal.call(recorded_stores[0].publishing.publish_connector, "supplier-write")
    assert api.client.portal.call(recorded_stores[1].publishing.is_published, "supplier-write")
    response = api.client.get("/api/me/catalogue", headers=api.headers("unmapped"))
    assert response.status_code == 200
    assert response.json()["connectors"] == []
    assert len(recorded_stores) == 3
    api.client.put(
        "/api/admin/mcp-permissions/groups/team/permissions", headers=api.admin_headers,
        json={"connectors": [{"connector_id": api.connector_id, "permission_status": "disabled"}]},
    ).raise_for_status()
    response = api.client.get("/api/me/catalogue", headers=api.headers("alice"))
    assert response.status_code == 200
    assert response.json()["connectors"] == []
    assert len(recorded_stores) == 4


async def authorize_owner(stores: DownstreamMcpStores, key: PersonalConnectionKey) -> None:
    configuration = await stores.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id=key.connector_id))
    connection = await stores.personal_connections.get(key)
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    grant = PersonalOAuthGrant(
        version=2, key=key, issuer="https://issuer.example", resource="https://tools.example/mcp", client_id="public-client",
        token_endpoint="https://issuer.example/token", redirect_uri="https://umbod.example/api/oauth/downstream-mcp/callback",
        client_mode="dynamic_public", token_endpoint_auth_method="none", requested_scopes=(), granted_scopes=(),
        configuration_revision=configuration.policy.revision, issued_at=now,
        lifetime=ExpiringPersonalToken(expires_at=now + timedelta(hours=1)),
        access_token=SecretStr("owner-token"), refresh_token=AbsentPersonalRefreshToken(),
    )
    await stores.personal_connections.replace_authorization(ReplacePersonalAuthorization(
        key=key, expected_revision=connection.revision, authorization=authorize_personal_grant(grant),
    ))


@pytest.mark.parametrize("revocation", ["enablement", "authorization"])
def test_owner_revocation_is_visible_on_next_catalogue_without_cross_caller_metadata(
    personal_api: PersonalApi, recorded_stores: list[DownstreamMcpStores], revocation: str,
) -> None:
    api = personal_api
    api.settings.connector_security.configuration_secret = LOCAL_DOWNSTREAM_MCP_CREDENTIAL_SECRET
    api.settings.personal_connections.oauth_enabled = True
    APISettings.model_validate(api.settings.model_dump())
    api.client.get("/api/me/catalogue", headers=api.headers("alice")).raise_for_status()
    transport = InMemoryPersonalMcpTransport()
    for subject in ("alice", "bob"):
        api.client.put(api.url + "/enablement", headers=api.headers(subject), json={"enabled": True}).raise_for_status()
        key = PersonalConnectionKey(
            principal=CanonicalPrincipal(namespace=api.settings.personal_connections.identity_namespace, subject=subject),
            connector_id=api.connector_id,
        )
        api.client.portal.call(authorize_owner, recorded_stores[0], key)
        transport.inventories[key] = PersonalToolInventory(tools=(DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id=api.connector_id, downstream_name="lookup"),
            title=subject + " private title", description=subject + " private description", input_schema={},
        ),))

    def provide_transport() -> InMemoryPersonalMcpTransport:
        return transport

    api.personal_app.dependency_overrides[get_personal_tool_transport] = provide_transport
    try:
        for subject in ("alice", "bob"):
            api.client.post(api.url + "/tools/discovery", headers=api.headers(subject), json={}).raise_for_status()
        alice = api.client.get("/api/me/catalogue", headers=api.headers("alice"))
        assert alice.status_code == 200
        assert alice.json()["connectors"][0]["capabilities"][0]["name"] == "alice private title"
        assert "bob private" not in alice.text
        if revocation == "enablement":
            api.client.put(api.url + "/enablement", headers=api.headers("alice"), json={"enabled": False}).raise_for_status()
        else:
            api.client.delete(api.url + "/authorization", headers=api.headers("alice")).raise_for_status()
        alice = api.client.get("/api/me/catalogue", headers=api.headers("alice"))
        bob = api.client.get("/api/me/catalogue", headers=api.headers("bob"))
        assert alice.status_code == bob.status_code == 200
        assert alice.json()["connectors"][0]["capabilities"] == []
        assert bob.json()["connectors"][0]["capabilities"][0]["name"] == "bob private title"
        assert "alice private" not in bob.text
        assert len(transport.list_requests) == 2
        assert transport.calls == []
    finally:
        del api.personal_app.dependency_overrides[get_personal_tool_transport]


@pytest.mark.parametrize("failure", [ValueError("secret-settings-canary"), RuntimeError("secret-construction-canary")])
def test_personal_supplier_failure_is_not_partial_success_or_retried(
    personal_api: PersonalApi, failure: Exception,
) -> None:
    api = personal_api
    supplier = FailingPersonalCatalogueStoreSupplier(failure)

    def provide_supplier() -> PersonalCatalogueStoreSupplier:
        return supplier

    api.personal_app.dependency_overrides[get_personal_catalogue_store_supplier] = provide_supplier
    try:
        async def request() -> httpx.Response:
            transport = httpx.ASGITransport(app=api.client.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.get("/api/me/catalogue", headers=api.headers("alice"))

        response = asyncio.run(request())
        assert response.status_code == 500
        assert response.headers["cache-control"] == "no-store"
        assert "secret-" not in response.text
        assert "connectors" not in response.json()
        assert supplier.calls == 1
    finally:
        del api.personal_app.dependency_overrides[get_personal_catalogue_store_supplier]
    response = api.client.get("/api/me/catalogue", headers=api.headers("alice"))
    assert response.status_code == 200
    assert len(response.json()["connectors"]) == 1
