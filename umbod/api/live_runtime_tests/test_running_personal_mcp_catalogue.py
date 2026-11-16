from uuid import uuid4

import httpx

from conftest import RuntimeEndpoints


def test_unvalidated_personal_mcp_is_not_exposed_to_end_users(
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
            publication = client.put(admin_url + "/publication")
            assert publication.status_code == 409
            assert publication.json()["detail"]["code"] == "personal_oauth_setup_required"
            assert client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "enabled",
            }]}).status_code == 404
            assert client.get(personal_url).status_code == 404
            assert client.put(personal_url + "/enablement", json={"enabled": True}).status_code == 404
            assert client.get(admin_url).json()["publication_status"] == "unpublished"
        finally:
            client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "disabled",
            }]})
            client.delete(admin_url + "/publication")
            client.delete(admin_url)
