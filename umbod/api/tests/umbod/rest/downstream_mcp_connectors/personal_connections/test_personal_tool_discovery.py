import asyncio
import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from umbod.config import AppConfig
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey, ReplacePersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import AbsentPersonalRefreshToken, ExpiringPersonalToken, PersonalOAuthGrant, authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalToolInventory
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationQuery
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, DownstreamMcpStores, create_downstream_mcp_stores
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from umbod.rest.main import create_app
from umbod.rest.connectors.downstream_mcp.personal_connections.tools import get_personal_tool_transport

from test_personal_connection_routes import PersonalApi, UserVerifier, _create_connector
from test_personal_tools_api import tool


@pytest.fixture
def discovery_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[PersonalApi]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "discovery.sqlite")},
        connector_security={"configuration_secret": "test-runtime-root-secret"},
        rest={"metrics_enabled": False},
        admin_authentication={"mode": "jwt", "environment": "development", "required_membership": "admins", "membership_claim": "groups", "jwt_header_name": "X-Access"},
        mcp={"permission_group_claim": "groups"},
        personal_connections={"enabled": True, "oauth_enabled": True, "identity_namespace": "test:personal-api"},
    )
    app = create_app(settings, [], user_verifier=UserVerifier())
    personal_app = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/me")
    admin_headers = {"X-Access": json.dumps({"signature": "trusted", "claims": {"sub": "admin", "groups": ["admins"]}})}
    with TestClient(app) as client:
        connector_id = _create_connector(client, admin_headers, "discovery")
        client.put(f"/api/admin/connectors/mcp/{connector_id}/publication", headers=admin_headers).raise_for_status()
        client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=admin_headers, json={"connectors": [{"connector_id": connector_id, "permission_status": "enabled"}]}).raise_for_status()
        for subject in ("alice", "bob"):
            client.put(f"/api/me/connectors/mcp/{connector_id}/enablement", headers={"X-Access": subject}, json={"enabled": True}).raise_for_status()
        yield PersonalApi(client, settings, admin_headers, connector_id, personal_app)


def query(api: PersonalApi, subject: str) -> PersonalRuntimeAuthorizationQuery:
    return PersonalRuntimeAuthorizationQuery(key=PersonalConnectionKey(principal=CanonicalPrincipal(namespace=api.settings.personal_connections.identity_namespace, subject=subject), connector_id=api.connector_id), group_ids=("team",), now=datetime.now(timezone.utc))


async def stores_with_grants(api: PersonalApi) -> DownstreamMcpStores:
    runtime = ConfiguredPersistenceRuntimeProvider(api.settings.connector_store).create()
    await runtime.readiness.ensure_ready()
    stores = await create_downstream_mcp_stores(api.settings.connector_security.configuration_secret, runtime.database)
    configuration = await stores.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id=api.connector_id))
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    for subject in ("alice", "bob"):
        key = query(api, subject).key
        connection = await stores.personal_connections.get(key)
        grant = PersonalOAuthGrant(
            version=2, key=key, issuer="https://issuer.example", resource="https://tools.example/mcp", client_id="public-client",
            token_endpoint="https://issuer.example/token", redirect_uri="https://umbod.example/api/oauth/downstream-mcp/callback",
            client_mode="dynamic_public", token_endpoint_auth_method="none", requested_scopes=(), granted_scopes=(),
            configuration_revision=configuration.policy.revision, issued_at=now, lifetime=ExpiringPersonalToken(expires_at=now + timedelta(hours=1)),
            access_token=SecretStr("test-user-token-" + subject), refresh_token=AbsentPersonalRefreshToken(),
        )
        await stores.personal_connections.replace_authorization(ReplacePersonalAuthorization(key=key, expected_revision=connection.revision, authorization=authorize_personal_grant(grant)))
    await stores.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=api.connector_id, capability_kind="tool", capability_key="lookup"), ActivationStatus.ENABLED)
    return stores


def test_verified_discovery_is_private_and_does_not_approve_or_execute(discovery_api: PersonalApi) -> None:
    api = discovery_api
    policy_url = f"/api/admin/connectors/mcp/{api.connector_id}/personal-tools"
    current = api.client.get(policy_url, headers=api.admin_headers).json()
    api.client.put(policy_url, headers=api.admin_headers, json={"expected_revision": current["revision"], "tools": [tool(api.connector_id)]}).raise_for_status()
    stores = asyncio.run(stores_with_grants(api))
    api.client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=api.admin_headers, json={"capabilities": [{"connector_id": api.connector_id, "capability_kind": "tool", "capability_key": "lookup", "permission_status": "enabled"}]}).raise_for_status()
    transport = InMemoryPersonalMcpTransport()
    observed = DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=api.connector_id, downstream_name="lookup"), title="Private Alice title", description="private-alice-description", input_schema={"type": "object", "properties": {"query": {"type": "string"}}})
    transport.inventories[query(api, "alice").key] = PersonalToolInventory(tools=(observed,))
    transport.inventories[query(api, "bob").key] = PersonalToolInventory(tools=())

    def provide_transport() -> InMemoryPersonalMcpTransport:
        return transport

    api.personal_app.dependency_overrides[get_personal_tool_transport] = provide_transport
    for subject in ("alice", "bob"):
        response = api.client.post(api.url + "/tools/discovery", headers=api.headers(subject), json={})
        assert response.status_code == 204
    assert len(asyncio.run(stores.personal_tool_access.list_available(query(api, "alice")))) == 1
    assert asyncio.run(stores.personal_tool_access.list_available(query(api, "bob"))) == ()
    catalogue = asyncio.run(stores.catalogs.get(ConnectorIdQuery(connector_id=api.connector_id)))
    assert catalogue.snapshot.tools[0].description == "Approved lookup"
    assert "private-alice" not in api.client.get(policy_url, headers=api.admin_headers).text
    assert transport.calls == []
    list_count = len(transport.list_requests)
    for subject, available in (("alice", True), ("bob", False)):
        assert api.client.get(api.url, headers=api.headers(subject)).json()["runtime_available"] is available
        selections = api.client.get("/api/me/connectors/mcp", headers=api.headers(subject)).json()["connectors"]
        assert next(item for item in selections if item["connector_id"] == api.connector_id)["runtime_available"] is available
    assert len(transport.list_requests) == list_count
    api.client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=api.admin_headers, json={"connectors": [{"connector_id": api.connector_id, "permission_status": "disabled"}]}).raise_for_status()
    assert asyncio.run(stores.personal_tool_access.list_available(query(api, "alice"))) == ()
    assert api.client.get(api.url, headers=api.headers("alice")).status_code == 404
