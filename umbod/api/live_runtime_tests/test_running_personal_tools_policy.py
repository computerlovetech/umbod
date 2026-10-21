import httpx

from test_running_personal_oauth_policy import personal_policy_client as personal_policy_client


def contract(connector_id: str) -> dict[str, object]:
    return {"identity": {"connector_id": connector_id, "downstream_name": "lookup"}, "title": "Approved lookup", "description": "Administrator supplied contract", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}, "output_schema_status": "absent"}


def test_personal_tool_schema_change_clears_activation_and_capability_grants(personal_policy_client: tuple[httpx.Client, str]) -> None:
    client, connector_id = personal_policy_client
    admin_url = f"/api/admin/connectors/mcp/{connector_id}"
    url = admin_url + "/personal-tools"
    initial = client.get(url)
    assert initial.status_code == 200
    assert initial.json()["tools"] == []
    approved = contract(connector_id)
    saved = client.put(url, json={"expected_revision": initial.json()["revision"], "tools": [approved]})
    assert saved.status_code == 200
    assert client.put(admin_url + "/tools/activation", json={"tools": [{"tool_id": "lookup", "activation_status": "enabled"}]}).status_code == 200
    permissions_url = "/api/admin/mcp-permissions/groups/admin/permissions"
    assert client.put(permissions_url, json={"capabilities": [{"connector_id": connector_id, "capability_kind": "tool", "capability_key": "lookup", "permission_status": "enabled"}]}).status_code == 200
    assert client.put(f"/api/me/connectors/mcp/{connector_id}/enablement", json={"enabled": True}).status_code == 200
    approved["input_schema"] = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    changed = client.put(url, json={"expected_revision": saved.json()["revision"], "tools": [approved]})
    assert changed.status_code == 200
    assert changed.json()["revision"] != saved.json()["revision"]
    activations = client.get(admin_url + "/tools/activation")
    assert activations.status_code == 200
    assert activations.json()["tools"][0]["activation_status"] == "disabled"
    permissions = client.get("/api/admin/mcp-permissions/groups/admin")
    assert permissions.status_code == 200
    assert connector_id in permissions.json()["connector_ids"]
    assert not any(item["connector_id"] == connector_id for item in permissions.json()["capabilities"])
    selection = client.get(f"/api/me/connectors/mcp/{connector_id}").json()
    assert selection["enabled"] is True
    assert selection["runtime_available"] is False
    assert client.put(url, json={"expected_revision": saved.json()["revision"], "tools": []}).status_code == 409


def test_personal_tool_policy_validation_and_cookie_checks_are_secret_free(personal_policy_client: tuple[httpx.Client, str]) -> None:
    client, connector_id = personal_policy_client
    url = f"/api/admin/connectors/mcp/{connector_id}/personal-tools"
    initial = client.get(url).json()
    body = {"expected_revision": initial["revision"], "tools": [], "client_secret": "runtime-client-secret-must-not-be-reflected"}
    invalid = client.put(url, json=body)
    assert invalid.status_code == 422
    assert "runtime-client-secret-must-not-be-reflected" not in invalid.text
    rejected = client.put(url, headers={"Cookie": "session=runtime", "Origin": "https://untrusted.invalid"}, json={"expected_revision": initial["revision"], "tools": []})
    assert rejected.status_code == 403
    assert client.get(url).json() == initial


def test_personal_discovery_never_substitutes_admin_client_credentials(personal_policy_client: tuple[httpx.Client, str]) -> None:
    client, connector_id = personal_policy_client
    url = f"/api/admin/connectors/mcp/{connector_id}/personal-tools"
    current = client.get(url).json()
    assert client.put(url, json={"expected_revision": current["revision"], "tools": [contract(connector_id)]}).status_code == 200
    personal_url = f"/api/me/connectors/mcp/{connector_id}"
    assert client.put(personal_url + "/enablement", json={"enabled": True}).status_code == 200
    denied = client.post(personal_url + "/tools/discovery", json={})
    assert denied.status_code == 409
    assert "127.0.0.1" not in denied.text
    assert "runtime-client-secret-must-not-be-reflected" not in denied.text
    invalid = client.post(personal_url + "/tools/discovery", json={"owner": "other", "authorization": "runtime-client-secret-must-not-be-reflected"})
    assert invalid.status_code == 422
    assert "runtime-client-secret-must-not-be-reflected" not in invalid.text
    with httpx.Client(base_url=str(client.base_url)) as anonymous:
        assert anonymous.post(personal_url + "/tools/discovery", json={}).status_code == 401
