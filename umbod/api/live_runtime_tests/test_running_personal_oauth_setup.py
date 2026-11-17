import os
import ssl
from uuid import uuid4

import httpx
import pytest

from conftest import RuntimeEndpoints


ISSUER = "https://personal-runtime.kind.invalid"


@pytest.mark.parametrize("metadata_mode,automatic_registration,methods,proposal_kind,proposal_method", [
    ("preview_oauth", "available", ["none", "client_secret_basic"], "dynamic_public", ""),
    ("preview_openid", "available", ["none", "client_secret_basic"], "dynamic_public", ""),
    ("preview_no_registration", "unavailable", ["none", "client_secret_basic"], "unavailable", ""),
    ("confidential_only", "available", ["client_secret_post", "client_secret_basic"], "dynamic_confidential", "client_secret_basic"),
    ("confidential_basic", "available", ["client_secret_basic"], "dynamic_confidential", "client_secret_basic"),
    ("confidential_post", "available", ["client_secret_post"], "dynamic_confidential", "client_secret_post"),
])
def test_unsaved_discovery_reads_metadata_without_registration_or_inventory_changes(
    runtime_endpoints: RuntimeEndpoints, metadata_mode: str, automatic_registration: str,
    methods: list[str], proposal_kind: str, proposal_method: str,
) -> None:
    context = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers, timeout=90) as client, httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=context, timeout=30,
    ) as provider:
        before_inventory = {connector["connector_id"] for connector in client.get("/api/admin/connectors/mcp").json()["connectors"]}
        changed = provider.post("/control", json={"owner": "metadata", "mode": metadata_mode})
        assert changed.status_code == 200
        before = changed.json()
        try:
            discovered = client.post("/api/admin/connectors/mcp/personal-oauth/discovery", json={
                "endpoint_url": ISSUER + "/mcp", "issuer_selection": {"kind": "automatic"},
            })
            assert discovered.status_code == 200
            assert discovered.headers["cache-control"] == "no-store"
            document = discovered.json()
            proposal = document.pop("automatic_client")
            assert proposal["kind"] == proposal_kind
            if proposal_kind != "unavailable":
                assert proposal["approved_issuers"] == [ISSUER]
            if proposal_method:
                assert proposal["token_endpoint_auth_method"] == proposal_method
            assert "client_id" not in proposal
            assert "client_secret" not in proposal
            assert document == {
                "kind": "discovered", "endpoint_url": ISSUER + "/mcp", "issuer_url": ISSUER,
                "available_scopes": ["read"], "scope_source": "resource",
                "automatic_registration": automatic_registration,
                "token_endpoint_auth_methods": methods,
            }
            assert provider.get("/control").json() == before
            after_inventory = {connector["connector_id"] for connector in client.get("/api/admin/connectors/mcp").json()["connectors"]}
            assert after_inventory == before_inventory
        finally:
            assert provider.post("/control", json={"owner": "metadata", "mode": "normal"}).status_code == 200


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
            unapproved = client.post(setup + "/validation", json={"expected_revision": client.get(setup).json()["revision"]})
            assert unapproved.status_code == 200
            assert unapproved.json()["state"]["status"] == "validated"
            assert unapproved.json()["state"]["result"]["scope_source"] == "not_checked"
            assert unapproved.json()["state"]["result"]["returned_scopes"] == []
            assert "kind-personal-client" not in unapproved.text
            assert client.get(policy_url).json()["requested_scopes"] == []
            assert provider.get("/control").json() == before
            approved = client.put(policy_url, json={
                "expected_revision": policy["revision"],
                "settings": {"requested_scopes": ["read"], "client": {"kind": "dynamic_public", "approved_issuers": [ISSUER]}},
            })
            assert approved.status_code == 200
            assert client.get(policy_url).json()["client"] == {"kind": "dynamic_public", "approved_issuers": [ISSUER]}
            assert client.get(setup).json()["state"]["status"] == "required"
            assert client.put(admin + "/publication").status_code == 409
            validated = client.post(setup + "/validation", json={"expected_revision": client.get(setup).json()["revision"]})
            assert validated.status_code == 200
            assert validated.json()["state"]["status"] == "validated"
            assert validated.json()["state"]["result"]["scope_source"] == "not_checked"
            assert validated.json()["state"]["result"]["returned_scopes"] == []
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
            assert after == before
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
