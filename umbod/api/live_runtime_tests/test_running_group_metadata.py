from uuid import uuid4

import httpx

from conftest import RuntimeEndpoints


def test_group_metadata_roundtrip_preserves_identity_permissions_and_registration(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = " ../development/" + uuid4().hex + " "
    groups_path = "/api/admin/groups"
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        registered = client.post(groups_path, json={
            "group_id": group_id, "label": "Development team", "description": "Maintains Umbod",
        })
        assert registered.status_code == 204, registered.text
        try:
            permissions = client.get(
                "/api/admin/mcp-permissions/group-permissions", params={"group_id": group_id},
            )
            assert permissions.status_code == 200, permissions.text
            updated = client.put(groups_path, json={
                "group_id": group_id, "label": "Engineering team", "description": "Builds Umbod",
                "expected_revision": 1,
            })
            assert updated.status_code == 200, updated.text
            expected = {
                "group_id": group_id, "label": "Engineering team", "description": "Builds Umbod",
                "revision": 2,
            }
            assert updated.json() == expected
            stale = client.put(groups_path, json={
                "group_id": group_id, "label": "Obsolete label", "description": "",
                "expected_revision": 1,
            })
            assert stale.status_code == 409, stale.text
            duplicate = client.post(groups_path, json={"group_id": group_id})
            assert duplicate.status_code == 204, duplicate.text
            catalogue = client.get(groups_path)
            assert catalogue.status_code == 200, catalogue.text
            assert expected in catalogue.json()["groups"]
            unchanged_permissions = client.get(
                "/api/admin/mcp-permissions/group-permissions", params={"group_id": group_id},
            )
            assert unchanged_permissions.status_code == 200, unchanged_permissions.text
            assert unchanged_permissions.json() == permissions.json()
        finally:
            removed = client.request("DELETE", groups_path, json={"group_id": group_id})
            assert removed.status_code == 204, removed.text


def test_group_metadata_update_rejects_untrusted_cookie_mutation(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = "metadata-csrf-" + uuid4().hex
    groups_path = "/api/admin/groups"
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as client:
        registered = client.post(groups_path, json={"group_id": group_id})
        assert registered.status_code == 204, registered.text
        try:
            rejected = client.put(groups_path, json={
                "group_id": group_id, "label": "Untrusted update", "description": "",
                "expected_revision": 1,
            }, headers={"Cookie": "web-session=runtime-test", "Origin": "https://untrusted.invalid"})
            assert rejected.status_code == 403, rejected.text
            catalogue = client.get(groups_path)
            assert catalogue.status_code == 200, catalogue.text
            assert {
                "group_id": group_id, "label": group_id, "description": "", "revision": 1,
            } in catalogue.json()["groups"]
        finally:
            removed = client.request("DELETE", groups_path, json={"group_id": group_id})
            assert removed.status_code == 204, removed.text
