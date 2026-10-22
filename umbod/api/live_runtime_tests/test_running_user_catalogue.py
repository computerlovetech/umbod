import httpx

from test_running_personal_oauth_policy import personal_policy_client as personal_policy_client


def test_running_user_catalogue_is_safe_and_tracks_current_personal_eligibility(
    personal_policy_client: tuple[httpx.Client, str],
) -> None:
    client, connector_id = personal_policy_client
    response = client.get("/api/me/catalogue")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"identity_key", "personal_enabled", "connectors"}
    assert body["personal_enabled"] is True
    assert len(body["identity_key"]) == 64
    connector = next(item for item in body["connectors"] if item["connector_id"] == connector_id)
    assert connector == {
        "connector_id": connector_id, "kind": "downstream_mcp",
        "display_name": "Personal provider policy runtime",
        "capability_description": "Scoped configured-client policy verification",
        "ownership": "personal", "capabilities": [],
    }
    assert client.get("/api/me/catalogue").json()["identity_key"] == body["identity_key"]
    permissions = "/api/admin/mcp-permissions/groups/admin/permissions"
    client.put(permissions, json={"connectors": [{
        "connector_id": connector_id, "permission_status": "disabled",
    }]}).raise_for_status()
    refreshed = client.get("/api/me/catalogue").json()
    assert connector_id not in {item["connector_id"] for item in refreshed["connectors"]}
