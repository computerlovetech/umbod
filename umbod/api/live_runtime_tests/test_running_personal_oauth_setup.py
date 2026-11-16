import os
import ssl
from uuid import uuid4

import httpx

from conftest import RuntimeEndpoints


ISSUER = "https://personal-runtime.kind.invalid"


def test_default_scopes_are_approved_and_validated_before_publication_without_login(runtime_endpoints: RuntimeEndpoints) -> None:
    context = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers, timeout=90) as client, httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=context, timeout=30,
    ) as provider:
        created = client.post("/api/admin/connectors/mcp/personal-oauth", json={
            "metadata": {
                "display_name": "Controlled setup validation",
                "capability_description": "Login-free personal OAuth setup",
                "public_path": "/mcp/proxies/setup-" + uuid4().hex[:20],
            },
            "configuration": {
                "endpoint_url": ISSUER + "/mcp",
                "oauth_configuration": {"requested_scopes": [], "client": {"kind": "dynamic_public"}},
            },
        })
        assert created.status_code == 201
        connector_id = created.json()["connector_id"]
        admin = f"/api/admin/connectors/mcp/{connector_id}"
        policy_url = admin + "/personal-oauth"
        setup = policy_url + "/setup"
        personal = f"/api/me/connectors/mcp/{connector_id}"
        permissions = "/api/admin/mcp-permissions/groups/admin/permissions"
        try:
            before = provider.get("/control").json()
            policy = client.get(policy_url).json()
            assert client.put(admin + "/publication").status_code == 409
            discovered = client.post(setup + "/discovery", json={"expected_revision": client.get(setup).json()["revision"]})
            assert discovered.status_code == 200
            assert discovered.json()["state"]["discovery"]["available_scopes"] == ["read"]
            assert provider.get("/control").json()["registrations"] == before["registrations"]
            mismatch = client.post(setup + "/validation", json={"expected_revision": client.get(setup).json()["revision"]})
            assert mismatch.status_code == 200
            assert mismatch.json()["state"]["status"] == "scope_mismatch"
            assert mismatch.json()["state"]["result"]["returned_scopes"] == ["read"]
            assert "kind-personal-client" not in mismatch.text
            assert client.get(policy_url).json()["requested_scopes"] == []
            assert client.put(admin + "/publication").status_code == 409
            approved = client.put(policy_url, json={
                "expected_revision": policy["revision"],
                "settings": {"requested_scopes": ["read"], "client": {"kind": "dynamic_public"}},
            })
            assert approved.status_code == 200
            assert client.get(setup).json()["state"]["status"] == "required"
            assert client.put(admin + "/publication").status_code == 409
            validated = client.post(setup + "/validation", json={"expected_revision": client.get(setup).json()["revision"]})
            assert validated.status_code == 200
            assert validated.json()["state"]["status"] == "validated"
            assert validated.json()["state"]["result"]["scope_source"] == "registration"
            assert client.put(admin + "/publication").status_code == 200
            assert client.put(permissions, json={"connectors": [{"connector_id": connector_id, "permission_status": "enabled"}]}).status_code == 200
            selected = client.get(personal)
            assert selected.status_code == 200
            assert selected.json()["enabled"] is False
            assert selected.json()["has_authorization"] is False
            enabled = client.put(personal + "/enablement", json={"enabled": True})
            assert enabled.status_code == 200
            assert enabled.json()["has_authorization"] is False
            after = provider.get("/control").json()
            assert after["registrations"] == before["registrations"] + 2
            for counter in ("authorizations", "exchanges", "refreshes", "discoveries", "calls"):
                assert after[counter] == before[counter]
            changed = client.put(policy_url, json={
                "expected_revision": approved.json()["revision"],
                "settings": {"requested_scopes": [], "client": {"kind": "dynamic_public"}},
            })
            assert changed.status_code == 200
            assert client.get(admin).json()["publication_status"] == "unpublished"
            assert client.get(personal).status_code == 404
            assert client.put(admin + "/publication").status_code == 409
        finally:
            assert client.put(permissions, json={"connectors": [{"connector_id": connector_id, "permission_status": "disabled"}]}).status_code == 200
            assert client.delete(admin + "/publication").status_code == 200
            assert client.delete(admin).status_code == 204
