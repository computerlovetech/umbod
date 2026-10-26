import asyncio

import pytest

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.capabilities.domain import CapabilityOutputSchema
from umbod.core.capabilities import AbsentCapabilityOutputSchema, PresentCapabilityOutputSchema
from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredToolWithoutOutputSchema, DiscoveredToolWithOutputSchema, ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory
from umbod.rest.connectors.downstream_mcp.personal_connections.tools import get_personal_tool_transport

from test_personal_connection_routes import PersonalApi, personal_api as personal_api
from test_personal_tool_discovery import discovery_api as discovery_api, query, stores_with_grants


def test_user_catalogue_exposes_safe_personal_selection_without_tools(personal_api: PersonalApi) -> None:
    response = personal_api.client.get("/api/me/catalogue", headers=personal_api.headers("alice"))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"identity_key", "personal_enabled", "connectors"}
    assert body["personal_enabled"] is True
    assert body["connectors"] == [{
        "connector_id": personal_api.connector_id, "kind": "downstream_mcp",
        "display_name": "Personal", "capability_description": "Personal account capabilities",
        "ownership": "personal", "capabilities": [],
    }]


def test_catalogue_identity_is_stable_and_changes_between_verified_subjects(personal_api: PersonalApi) -> None:
    client = personal_api.client
    alice = client.get("/api/me/catalogue", headers=personal_api.headers("alice")).json()["identity_key"]
    repeated = client.get("/api/me/catalogue", headers=personal_api.headers("alice")).json()["identity_key"]
    bob = client.get("/api/me/catalogue", headers=personal_api.headers("bob")).json()["identity_key"]
    assert alice == repeated
    assert alice != bob
    assert len(alice) == 64
    assert "alice" not in alice


def test_personal_identity_mapping_failure_does_not_deny_general_catalogue(personal_api: PersonalApi) -> None:
    response = personal_api.client.get("/api/me/catalogue", headers=personal_api.headers("unmapped"))
    assert response.status_code == 200
    assert response.json()["connectors"] == []


def test_catalogue_reflects_permission_withdrawal(personal_api: PersonalApi) -> None:
    personal_api.client.put(
        "/api/admin/mcp-permissions/groups/team/permissions",
        headers=personal_api.admin_headers,
        json={"connectors": [{"connector_id": personal_api.connector_id, "permission_status": "disabled"}]},
    ).raise_for_status()
    assert personal_api.client.get(
        "/api/me/catalogue", headers=personal_api.headers("alice"),
    ).json()["connectors"] == []


@pytest.mark.parametrize("output_schema", [
    AbsentCapabilityOutputSchema(),
    PresentCapabilityOutputSchema(schema={"type": "object", "properties": {"result": {"type": "string"}}}),
])
def test_owner_catalogue_reads_private_observations_without_discovery_or_invocation(
    discovery_api: PersonalApi, output_schema: CapabilityOutputSchema,
) -> None:
    api = discovery_api
    asyncio.run(stores_with_grants(api))
    transport = InMemoryPersonalMcpTransport()
    metadata = {
        "identity": ToolIdentity(connector_id=api.connector_id, downstream_name="lookup"),
        "title": "Alice display title", "description": "Alice private description",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        "annotations": {"readOnlyHint": True}, "meta": {"private_observation": "not-public"},
    }
    observed = (
        DiscoveredToolWithOutputSchema(**metadata, output_schema=output_schema.schema_)
        if output_schema.status == "present" else DiscoveredToolWithoutOutputSchema(**metadata)
    )
    transport.inventories[query(api, "alice").key] = PersonalToolInventory(tools=(observed,))

    def provide_transport() -> InMemoryPersonalMcpTransport:
        return transport

    api.personal_app.dependency_overrides[get_personal_tool_transport] = provide_transport
    api.client.post(api.url + "/tools/discovery", headers=api.headers("alice"), json={}).raise_for_status()
    discovery_count = len(transport.list_requests)
    alice = api.client.get("/api/me/catalogue", headers=api.headers("alice")).json()
    bob = api.client.get("/api/me/catalogue", headers=api.headers("bob")).json()
    assert alice["connectors"][0]["capabilities"] == [{
        "kind": "tool", "key": "lookup", "name": "Alice display title",
        "description": "Alice private description",
        "input_schema": observed.input_schema, "output_schema": output_schema.model_dump(mode="json"),
    }]
    assert bob["connectors"][0]["capabilities"] == []
    assert "private_observation" not in str(alice)
    assert "test-user-token" not in str(alice)
    assert len(transport.list_requests) == discovery_count
    assert transport.calls == []


def test_anonymous_catalogue_and_documentation_require_authentication(personal_api: PersonalApi) -> None:
    for path in ("/catalogue", "/docs", "/openapi.json"):
        response = personal_api.client.get("/api/me" + path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
