from uuid import uuid4

import httpx

from conftest import RuntimeEndpoints


def test_personal_setup_rejects_private_provider_before_publication(
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
        setup_url = admin_url + "/personal-oauth/setup"
        personal_url = f"/api/me/connectors/mcp/{connector_id}"
        try:
            policy = client.get(admin_url + "/personal-oauth").json()
            assert client.get(setup_url).json()["state"]["status"] == "required"
            assert client.put(admin_url + "/publication").status_code == 409
            blocked = client.post(setup_url + "/validation", headers={
                "Cookie": "session=runtime", "Origin": "https://untrusted.invalid",
            }, json={"expected_revision": policy["revision"]})
            assert blocked.status_code == 403
            failed = client.post(setup_url + "/validation", json={"expected_revision": client.get(setup_url).json()["revision"]})
            assert failed.status_code == 200
            assert failed.json()["state"]["status"] == "failed"
            assert "127.0.0.1" not in failed.text
            assert client.put(admin_url + "/publication").status_code == 409
            assert client.get(personal_url).status_code == 404
            assert client.post(personal_url + "/oauth/attempts", json={}).status_code == 404
            assert client.get(admin_url).json()["publication_status"] == "unpublished"
        finally:
            assert client.delete(admin_url).status_code == 204


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
