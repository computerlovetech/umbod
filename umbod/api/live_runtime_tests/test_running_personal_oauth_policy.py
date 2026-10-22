from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest

from conftest import RuntimeEndpoints


CLIENT_SECRET = "runtime-client-secret-must-not-be-reflected"
ROTATED_CLIENT_SECRET = "runtime-rotated-client-secret-must-not-be-reflected"


def _confidential_settings(secret: str) -> dict[str, object]:
    return {
        "requested_scopes": ["documents.read"],
        "client": {
            "kind": "preconfigured_confidential",
            "issuer_url": "https://issuer.runtime.invalid",
            "client_id": "runtime-personal-client",
            "token_endpoint_auth_method": "client_secret_basic",
            "client_secret": secret,
        },
    }


@pytest.fixture
def personal_policy_client(
    runtime_endpoints: RuntimeEndpoints,
) -> Iterator[tuple[httpx.Client, str]]:
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        created = client.post("/api/admin/connectors/mcp/personal-oauth", json={
            "metadata": {
                "display_name": "Personal provider policy runtime",
                "capability_description": "Scoped configured-client policy verification",
                "public_path": f"/mcp/proxies/policy-{uuid4().hex}",
            },
            "configuration": {
                "endpoint_url": "https://127.0.0.1/mcp",
                "oauth_configuration": _confidential_settings(CLIENT_SECRET),
            },
        })
        assert created.status_code == 201
        assert CLIENT_SECRET not in created.text
        assert created.json()["credential_configured"] is False
        connector_id = created.json()["connector_id"]
        admin_url = f"/api/admin/connectors/mcp/{connector_id}"
        permissions_url = "/api/admin/mcp-permissions/groups/admin/permissions"
        try:
            assert client.put(admin_url + "/publication").status_code == 200
            assert client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "enabled",
            }]}).status_code == 200
            yield client, connector_id
        finally:
            client.put(permissions_url, json={"connectors": [{
                "connector_id": connector_id, "permission_status": "disabled",
            }]})
            client.delete(admin_url + "/publication")
            client.delete(admin_url)


def test_personal_oauth_policy_rotation_is_revision_bound_and_secret_free(
    personal_policy_client: tuple[httpx.Client, str],
) -> None:
    client, connector_id = personal_policy_client
    policy_url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"
    personal_url = f"/api/me/connectors/mcp/{connector_id}"
    initial = client.get(policy_url)
    assert initial.status_code == 200
    assert initial.json()["requested_scopes"] == ["documents.read"]
    assert initial.json()["client"]["client_secret_configured"] is True
    assert "client_secret" not in initial.json()["client"]
    assert CLIENT_SECRET not in initial.text
    assert client.put(personal_url + "/enablement", json={"enabled": True}).status_code == 200
    rotated = client.put(policy_url, json={
        "expected_revision": initial.json()["revision"],
        "settings": _confidential_settings(ROTATED_CLIENT_SECRET),
    })
    assert rotated.status_code == 200
    assert rotated.json()["revision"] != initial.json()["revision"]
    assert CLIENT_SECRET not in rotated.text
    assert ROTATED_CLIENT_SECRET not in rotated.text
    stale = client.put(policy_url, json={
        "expected_revision": initial.json()["revision"],
        "settings": {"requested_scopes": [], "client": {"kind": "dynamic_public"}},
    })
    assert stale.status_code == 409
    selection = client.get(personal_url)
    assert selection.status_code == 200
    assert selection.json()["enabled"] is True
    assert selection.json()["has_authorization"] is False
    assert selection.json()["runtime_available"] is False
    public = client.put(policy_url, json={
        "expected_revision": rotated.json()["revision"],
        "settings": {"requested_scopes": [], "client": {"kind": "dynamic_public"}},
    })
    assert public.status_code == 200
    assert public.json()["client"] == {"kind": "dynamic_public"}


def test_personal_oauth_policy_validation_and_cookie_checks_do_not_reflect_secrets(
    personal_policy_client: tuple[httpx.Client, str],
) -> None:
    client, connector_id = personal_policy_client
    policy_url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"
    initial = client.get(policy_url)
    assert initial.status_code == 200
    settings = _confidential_settings(ROTATED_CLIENT_SECRET)
    settings["unapproved_field"] = CLIENT_SECRET
    invalid = client.put(policy_url, json={
        "expected_revision": initial.json()["revision"], "settings": settings,
    })
    assert invalid.status_code == 422
    assert CLIENT_SECRET not in invalid.text
    assert ROTATED_CLIENT_SECRET not in invalid.text
    blocked = client.put(policy_url, headers={
        "Cookie": "session=runtime", "Origin": "https://untrusted.invalid",
    }, json={
        "expected_revision": initial.json()["revision"],
        "settings": _confidential_settings(ROTATED_CLIENT_SECRET),
    })
    assert blocked.status_code == 403
    assert ROTATED_CLIENT_SECRET not in blocked.text
    unchanged = client.get(policy_url)
    assert unchanged.status_code == 200
    assert unchanged.json() == initial.json()
    with httpx.Client(base_url=str(client.base_url)) as anonymous:
        assert anonymous.get(f"/api/me/connectors/mcp/{connector_id}").status_code == 200


def test_scoped_configured_client_still_rejects_private_provider_and_user_overrides(
    personal_policy_client: tuple[httpx.Client, str],
) -> None:
    client, connector_id = personal_policy_client
    personal_url = f"/api/me/connectors/mcp/{connector_id}"
    assert client.put(personal_url + "/enablement", json={"enabled": True}).status_code == 200
    overrides = client.post(personal_url + "/oauth/attempts", json={
        "client_secret": CLIENT_SECRET, "scope": "documents.write",
    })
    assert overrides.status_code == 422
    assert CLIENT_SECRET not in overrides.text
    rejected = client.post(personal_url + "/oauth/attempts", json={})
    assert rejected.status_code in (422, 502)
    assert CLIENT_SECRET not in rejected.text
    assert "127.0.0.1" not in rejected.text
    selection = client.get(personal_url)
    assert selection.status_code == 200
    assert selection.json()["has_authorization"] is False
    assert selection.json()["runtime_available"] is False
