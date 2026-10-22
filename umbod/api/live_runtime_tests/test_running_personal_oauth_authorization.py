from uuid import uuid4

import httpx

from conftest import RuntimeEndpoints


def test_personal_authorization_rejects_private_provider_without_authentication_changes(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        created = client.post("/api/admin/connectors/mcp/personal-oauth", json={
            "metadata": {
                "display_name": "Personal authorization runtime",
                "capability_description": "Personal authorization safety verification",
                "public_path": f"/mcp/proxies/personal-auth-{uuid4().hex[:24]}",
            },
            "configuration": {"endpoint_url": "https://127.0.0.1/mcp"},
        })
        assert created.status_code == 201
        connector_id = created.json()["connector_id"]
        admin_url = f"/api/admin/connectors/mcp/{connector_id}"
        personal_url = f"/api/me/connectors/mcp/{connector_id}"
        attempts_url = personal_url + "/oauth/attempts"
        permissions_url = "/api/admin/mcp-permissions/groups/admin/permissions"
        try:
            assert client.put(admin_url + "/publication").status_code == 200
            assert client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "enabled",
            }]}).status_code == 200
            assert client.post(attempts_url, json={}).status_code == 404
            assert client.put(personal_url + "/enablement", json={"enabled": True}).status_code == 200
            assert client.post(attempts_url, json={"scope": "administrator"}).status_code == 422
            assert client.post(attempts_url, headers={
                "Cookie": "session=runtime", "Origin": "https://untrusted.invalid",
            }, json={}).status_code == 403
            failed = client.post(attempts_url, json={})
            assert failed.status_code in (422, 502)
            assert "127.0.0.1" not in failed.text
            assert client.post(attempts_url, json={}).status_code == failed.status_code
            selection = client.get(personal_url)
            assert selection.status_code == 200
            assert selection.json()["has_authorization"] is False
            assert selection.json()["runtime_available"] is False
            assert client.get(attempts_url + "/" + uuid4().hex).status_code == 404
            with httpx.Client(base_url=runtime_endpoints.api_base_url) as anonymous:
                assert anonymous.get(personal_url).status_code == 200
        finally:
            client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "disabled",
            }]})
            client.delete(admin_url + "/publication")
            client.delete(admin_url)


def test_personal_authorization_callback_is_public_but_state_bound_and_secret_free(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    secret = "runtime-code-must-not-be-reflected"
    with httpx.Client(base_url=runtime_endpoints.api_base_url) as client:
        callback = client.get("/api/oauth/downstream-mcp/callback", params={
            "state": "0" * 32 + ".runtime-state-must-not-be-logged", "code": secret,
            "iss": "https://runtime-issuer-must-not-be-logged.invalid",
        })
        assert callback.status_code == 400
        assert "no-store" in callback.headers["cache-control"]
        assert callback.headers["referrer-policy"] == "no-referrer"
        assert secret not in callback.text
        assert "runtime-issuer-must-not-be-logged" not in callback.text
