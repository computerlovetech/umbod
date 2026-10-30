from urllib.parse import quote
from uuid import uuid4

import httpx
import pytest

from conftest import RuntimeEndpoints


def registered_group(group_id: str) -> dict[str, object]:
    return {"group_id": group_id, "label": group_id, "description": "", "revision": 1}


@pytest.mark.parametrize("group_id", [".", ".."])
def test_shared_group_dot_segment_ids_use_body_and_query_operations(
    runtime_endpoints: RuntimeEndpoints, group_id: str,
) -> None:
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        registered = client.post("/api/admin/groups", json={"group_id": group_id})
        assert registered.status_code == 204, registered.text
        try:
            permissions = client.get(
                "/api/admin/mcp-permissions/group-permissions", params={"group_id": group_id},
            )
            assert permissions.status_code == 200, permissions.text
            assert permissions.json() == {"group_id": group_id, "connector_ids": [], "capabilities": []}
            updated = client.put(
                "/api/admin/mcp-permissions/group-permissions",
                params={"group_id": group_id},
                json={"connectors": [{"connector_id": "unused", "permission_status": "disabled"}]},
            )
            assert updated.status_code == 200, updated.text
        finally:
            removed = client.request("DELETE", "/api/admin/groups", json={"group_id": group_id})
            assert removed.status_code == 204, removed.text


def test_shared_catalogue_preserves_exact_group_ids_with_slashes(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = " shared/" + uuid4().hex + " "
    path = "/api/admin/groups/" + quote(group_id, safe="")
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        registered = client.post("/api/admin/groups", json={"group_id": group_id})
        assert registered.status_code == 204, registered.text
        try:
            catalogue = client.get("/api/admin/groups")
            assert catalogue.status_code == 200, catalogue.text
            assert registered_group(group_id) in catalogue.json()["groups"]
            assert group_id.strip() not in [group["group_id"] for group in catalogue.json()["groups"]]
        finally:
            removed = client.delete(path)
            assert removed.status_code == 204, removed.text


def test_shared_group_registration_rejects_untrusted_cookie_mutation(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = "shared-csrf-" + uuid4().hex
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        rejected = client.post("/api/admin/groups", json={"group_id": group_id}, headers={
            "Cookie": "web-session=runtime-test", "Origin": "https://untrusted.invalid",
        })
        assert rejected.status_code == 403, rejected.text
        catalogue = client.get("/api/admin/groups")
        assert catalogue.status_code == 200, catalogue.text
        assert group_id not in [group["group_id"] for group in catalogue.json()["groups"]]


def test_legacy_group_registration_uses_shared_catalogue_with_independent_connector_usage(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = "shared-connector-" + uuid4().hex
    groups_path = "/api/admin/groups"
    connector_group_path = "/api/admin/mcp-permissions/groups/" + group_id
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        original_policy = client.get("/api/admin/filesystem/root-access")
        assert original_policy.status_code == 200, original_policy.text
        targets = client.get("/api/admin/mcp-permissions/assignable-targets")
        assert targets.status_code == 200, targets.text
        assert targets.json()["connectors"]
        connector_id = targets.json()["connectors"][0]["connector_id"]
        registered = client.post(connector_group_path)
        assert registered.status_code == 200, registered.text
        try:
            catalogue = client.get(groups_path)
            assert catalogue.status_code == 200, catalogue.text
            assert registered_group(group_id) in catalogue.json()["groups"]
            assigned = client.put(connector_group_path + "/permissions", json={
                "connectors": [{"connector_id": connector_id, "permission_status": "enabled"}],
            })
            assert assigned.status_code == 200, assigned.text
            blocked = client.delete(groups_path + "/" + group_id)
            assert blocked.status_code == 409, blocked.text
            policy = client.get("/api/admin/filesystem/root-access")
            assert policy.status_code == 200, policy.text
            assert policy.json() == original_policy.json()
        finally:
            cleared = client.put(connector_group_path + "/permissions", json={
                "connectors": [{"connector_id": connector_id, "permission_status": "disabled"}],
            })
            removed = client.delete(groups_path + "/" + group_id)
            assert cleared.status_code == 200, cleared.text
            assert removed.status_code == 204, removed.text


def test_shared_group_registration_and_independent_filesystem_usage(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = "shared-group-" + uuid4().hex
    groups_path = "/api/admin/groups"
    policy_path = "/api/admin/filesystem/root-access"
    connector_group_path = "/api/admin/mcp-permissions/groups/" + group_id
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        original = client.get(policy_path)
        assert original.status_code == 200, original.text
        original_groups = original.json()["groups"]
        registered = client.post(groups_path, json={"group_id": group_id})
        assert registered.status_code == 204, registered.text
        try:
            duplicate = client.post(groups_path, json={"group_id": group_id})
            assert duplicate.status_code == 204, duplicate.text
            catalogue = client.get(groups_path)
            assert catalogue.status_code == 200, catalogue.text
            assert catalogue.json()["groups"].count(registered_group(group_id)) == 1
            connector_groups = client.get("/api/admin/mcp-permissions/groups")
            assert connector_groups.status_code == 200, connector_groups.text
            assert {"group_id": group_id} in connector_groups.json()["groups"]
            connector_permissions = client.get(connector_group_path)
            assert connector_permissions.status_code == 200, connector_permissions.text
            assert connector_permissions.json()["connector_ids"] == []
            assert connector_permissions.json()["capabilities"] == []
            policy = client.get(policy_path)
            assert policy.status_code == 200, policy.text
            assert policy.json()["groups"] == original_groups
            assert policy.json()["revision"] == original.json()["revision"]
            assigned = client.put(policy_path, json={
                "expected_revision": policy.json()["revision"],
                "groups": [*original_groups, {
                    "group_id": group_id,
                    "permissions": ["read"],
                }],
            })
            assert assigned.status_code == 200, assigned.text
            blocked = client.delete(groups_path + "/" + group_id)
            assert blocked.status_code == 409, blocked.text
            legacy_blocked = client.delete(connector_group_path)
            assert legacy_blocked.status_code == 409, legacy_blocked.text
            reduced = client.put(policy_path, json={
                "expected_revision": assigned.json()["revision"],
                "groups": [*original_groups, {
                    "group_id": group_id,
                    "permissions": ["discover"],
                }],
            })
            assert reduced.status_code == 200, reduced.text
            still_blocked = client.delete(groups_path + "/" + group_id)
            assert still_blocked.status_code == 409, still_blocked.text
            unchanged = client.get(connector_group_path)
            assert unchanged.status_code == 200, unchanged.text
            assert unchanged.json() == connector_permissions.json()
        finally:
            current = client.get(policy_path)
            assert current.status_code == 200, current.text
            restored = client.put(policy_path, json={
                "expected_revision": current.json()["revision"], "groups": original_groups,
            })
            retained = client.get(groups_path)
            removed = client.delete(groups_path + "/" + group_id)
            assert restored.status_code == 200, restored.text
            assert removed.status_code == 204, removed.text
            assert retained.status_code == 200, retained.text
            assert registered_group(group_id) in retained.json()["groups"]
        remaining = client.get(groups_path)
        assert remaining.status_code == 200, remaining.text
        assert group_id not in [group["group_id"] for group in remaining.json()["groups"]]
