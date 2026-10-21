from uuid import uuid4

import httpx

from conftest import RuntimeEndpoints


def test_personal_mcp_available_by_default_preserves_explicit_user_opt_in(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        created = client.post("/api/admin/connectors/mcp/personal-oauth", json={
            "metadata": {
                "display_name": "Personal runtime", "capability_description": "Runtime personal catalogue verification",
                "public_path": f"/mcp/proxies/personal-{uuid4().hex}",
            },
            "configuration": {"endpoint_url": "https://personal-oauth-runtime.invalid/mcp"},
        })
        assert created.status_code == 201
        connector_id = created.json()["connector_id"]
        admin_url = f"/api/admin/connectors/mcp/{connector_id}"
        personal_url = f"/api/me/connectors/mcp/{connector_id}"
        permissions_url = "/api/admin/mcp-permissions/groups/admin/permissions"
        try:
            assert created.json()["credential_configured"] is False
            assert created.json()["health"]["status"] == "unknown"
            assert client.get(personal_url).status_code == 404
            assert client.put(admin_url + "/publication").status_code == 200
            assert client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "enabled",
            }]}).status_code == 200
            initial = client.get(personal_url)
            assert initial.status_code == 200
            assert initial.json()["enabled"] is False
            enabled = client.put(personal_url + "/enablement", json={"enabled": True})
            assert enabled.status_code == 200
            assert enabled.json()["enabled"] is True
            assert enabled.json()["has_authorization"] is False
            assert enabled.json()["runtime_available"] is False
            assert "endpoint_url" not in enabled.json()
            assert client.put(personal_url + "/enablement", headers={
                "Cookie": "session=runtime", "Origin": "https://untrusted.invalid",
            }, json={"enabled": False}).status_code == 403
            assert client.delete(personal_url + "/authorization").status_code == 204
            assert client.get(personal_url).json()["enabled"] is False
            with httpx.Client(base_url=runtime_endpoints.api_base_url) as anonymous:
                assert anonymous.get("/api/me/connectors/mcp").status_code == 401
        finally:
            client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "disabled",
            }]})
            client.delete(admin_url + "/publication")
            client.delete(admin_url)
