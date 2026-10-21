import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery
from umbod.rest.connectors.downstream_mcp.personal_connections.tools import get_personal_tool_discovery

from test_personal_connection_routes import PersonalApi, personal_api as personal_api


def tool(connector_id: str) -> dict[str, object]:
    return {"identity": {"connector_id": connector_id, "downstream_name": "lookup"}, "title": "Lookup", "description": "Approved lookup", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}, "output_schema_status": "absent"}


def test_admin_replaces_personal_tool_contracts_with_cas_without_enabling_runtime(personal_api: PersonalApi) -> None:
    client, headers = personal_api.client, personal_api.admin_headers
    url = f"/api/admin/connectors/mcp/{personal_api.connector_id}/personal-tools"
    initial = client.get(url, headers=headers)
    assert initial.status_code == 200
    assert initial.json()["tools"] == []
    request = {"expected_revision": initial.json()["revision"], "tools": [tool(personal_api.connector_id)]}
    changed = client.put(url, headers=headers, json=request)
    assert changed.status_code == 200
    assert len(changed.json()["tools"]) == 1
    assert changed.json()["revision"] != initial.json()["revision"]
    assert client.put(url, headers=headers, json=request).status_code == 409
    same = client.put(url, headers=headers, json={"expected_revision": changed.json()["revision"], "tools": changed.json()["tools"]})
    assert same.status_code == 200
    assert same.json()["revision"] == changed.json()["revision"]
    assert client.get(personal_api.url, headers=personal_api.headers("alice")).json()["runtime_available"] is False


@pytest.mark.parametrize("invalidity", ("foreign", "duplicate", "bad_schema", "secret_extra", "remote_ref"))
def test_admin_rejects_invalid_tool_contracts_without_reflecting_documents(personal_api: PersonalApi, invalidity: str) -> None:
    url = f"/api/admin/connectors/mcp/{personal_api.connector_id}/personal-tools"
    initial = personal_api.client.get(url, headers=personal_api.admin_headers).json()
    item = tool(personal_api.connector_id)
    request = {"expected_revision": initial["revision"], "tools": [item]}
    if invalidity == "foreign":
        item["identity"] = {"connector_id": "other", "downstream_name": "lookup"}
    elif invalidity == "duplicate":
        request["tools"] = [item, item]
    elif invalidity == "bad_schema":
        item["input_schema"] = {"type": "not-a-json-type"}
    elif invalidity == "remote_ref":
        item["input_schema"] = {"$ref": "https://private.example/schema"}
    else:
        request["client_secret"] = "invalid-tool-secret-never-reflected"
    response = personal_api.client.put(url, headers=personal_api.admin_headers, json=request)
    assert response.status_code == 422
    assert "invalid-tool-secret-never-reflected" not in response.text
    assert personal_api.client.get(url, headers=personal_api.admin_headers).json() == initial


class CaptureDiscovery:
    def __init__(self) -> None:
        self.calls: list[PersonalRuntimeAuthorizationQuery] = []

    async def discover(self, query: PersonalRuntimeAuthorizationQuery) -> None:
        self.calls.append(query)


@pytest.fixture
def discovery_capture(personal_api: PersonalApi) -> CaptureDiscovery:
    capture = CaptureDiscovery()

    def provide() -> CaptureDiscovery:
        return capture

    personal_api.personal_app.dependency_overrides[get_personal_tool_discovery] = provide
    return capture


def test_discovery_identity_and_groups_come_only_from_verified_request(personal_api: PersonalApi, discovery_capture: CaptureDiscovery) -> None:
    for subject in ("alice", "bob"):
        response = personal_api.client.post(personal_api.url + "/tools/discovery", headers=personal_api.headers(subject), json={})
        assert response.status_code == 204
        assert response.headers["cache-control"] == "no-store"
    assert [query.key.principal.subject for query in discovery_capture.calls] == ["alice", "bob"]
    assert all(query.group_ids == ("team",) for query in discovery_capture.calls)
    assert all(query.key.connector_id == personal_api.connector_id for query in discovery_capture.calls)


@pytest.mark.parametrize("body", ({"owner": "bob"}, {"scopes": ["admin"]}, {"authorization": "never-reflect-discovery-secret"}, {"padding": "x" * 4097}))
def test_discovery_rejects_overrides_without_io_or_secret_reflection(personal_api: PersonalApi, discovery_capture: CaptureDiscovery, body: dict[str, object]) -> None:
    response = personal_api.client.post(personal_api.url + "/tools/discovery", headers=personal_api.headers("alice"), json=body)
    assert response.status_code == 422
    assert "never-reflect-discovery-secret" not in response.text
    assert discovery_capture.calls == []


def test_discovery_authentication_and_administrator_separation(personal_api: PersonalApi, discovery_capture: CaptureDiscovery) -> None:
    assert personal_api.client.post(personal_api.url + "/tools/discovery", json={}).status_code == 401
    assert personal_api.client.post(personal_api.url + "/tools/discovery", headers=personal_api.headers("unmapped"), json={}).status_code == 403
    admin_url = f"/api/admin/connectors/mcp/{personal_api.connector_id}/personal-tools"
    assert personal_api.client.get(admin_url, headers={"X-Access": '{"signature":"trusted","claims":{"sub":"alice","groups":["team"]}}'}).status_code == 403
    assert discovery_capture.calls == []
