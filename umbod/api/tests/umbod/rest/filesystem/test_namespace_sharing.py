from uuid import UUID

import pytest

from umbod.core.filesystem.namespaces import SaveSharedNamespaceDescription
from umbod.infrastructure import create_filesystem_namespace_management

from .conftest import FilesystemHttp, create_shared_namespace, replace_shared_access
from .test_http_contract import BASE, BODY
from .test_sharing_routes import observed_user as observed_user, sharing_http as sharing_http


def test_namespace_discovery_and_root_browsing_share_canonical_description(sharing_http: FilesystemHttp) -> None:
    namespace = create_shared_namespace(sharing_http, "read_write")
    management = create_filesystem_namespace_management(database=sharing_http.factories.persistence_runtime.database, issuer="issuer")
    saved = sharing_http.client.portal.call(management.save, namespace.id, SaveSharedNamespaceDescription(name=namespace.name, groups=namespace.groups, description='Équipe "reference"', expected_revision=namespace.revision, expected_root_revision=namespace.root_revision))
    listing = sharing_http.client.get(BASE + "/namespaces")
    assert listing.status_code == 200
    summary = next(entry for entry in listing.json()["namespaces"] if entry["id"] == str(saved.id))
    assert summary["description"] == saved.description
    root = sharing_http.client.get(f"{BASE}/nodes/{saved.root_node_id}")
    assert root.status_code == 200
    assert root.json()["metadata"]["attributes"]["description"] == saved.description
    assert root.json()["revision"] == saved.root_revision
    assert "description" not in root.json()["visible_to"]


@pytest.mark.parametrize("kind", ["personal", "shared", "structural"])
def test_namespace_roots_are_not_item_sharing_targets(sharing_http: FilesystemHttp, kind: str) -> None:
    client = sharing_http.client
    if kind == "personal":
        node_id = client.post(BASE + "/home").json()["id"]
    elif kind == "shared":
        node_id = str(create_shared_namespace(sharing_http, "read_write").root_node_id)
    else:
        node_id = str(UUID(int=0))
    path = f"{BASE}/nodes/{node_id}/access"
    responses = [
        client.get(path), client.get(path + "/recipients", params={"query": "team"}),
        client.put(path, params={"recipient_type": "group"}, headers={"If-Match": '"opaque"'}, json={"grants": []}),
    ]
    assert all(response.status_code == 403 for response in responses)
    assert all(response.headers["cache-control"] == "no-store" for response in responses)


def test_item_shares_and_owner_remain_independent_of_shared_namespace_baseline(
    sharing_http: FilesystemHttp, observed_user: str,
) -> None:
    client = sharing_http.client
    namespace = create_shared_namespace(sharing_http, "read_write")
    node = client.post(f"{BASE}/nodes/{namespace.root_node_id}/directories", json=BODY).json()
    path = f"{BASE}/nodes/{node['id']}"
    access_path = path + "/access"
    bob = {"Authorization": "Bearer bob"}
    assert client.get(path, headers=bob).json()["permissions"]["can_write"] is True
    assert client.get(path, headers=bob).json()["permissions"]["can_share"] is False
    initial = client.get(access_path)
    narrowed = client.put(access_path, params={"recipient_type": "group"}, headers={"If-Match": initial.headers["etag"]}, json={
        "grants": [{"recipient": {"type": "group", "group_id": "team"}, "permissions": ["discover", "read"]}],
    })
    assert narrowed.status_code == 200
    assert client.get(path, headers=bob).json()["permissions"]["can_write"] is True
    cleared = client.put(access_path, params={"recipient_type": "group"}, headers={"If-Match": narrowed.headers["etag"]}, json={"grants": []})
    assert cleared.status_code == 200
    assert client.get(path, headers=bob).json()["permissions"]["can_write"] is True
    shared = client.put(access_path, params={"recipient_type": "user"}, headers={"If-Match": cleared.headers["etag"]}, json={
        "grants": [{"recipient": {"type": "user", "user_id": observed_user}, "permissions": ["discover", "read"]}],
    })
    assert shared.status_code == 200
    replace_shared_access(sharing_http, namespace, None)
    assert client.get(f"{BASE}/nodes/{namespace.root_node_id}", headers=bob).status_code == 403
    assert str(namespace.id) not in {entry["id"] for entry in client.get(BASE + "/namespaces", headers=bob).json()["namespaces"]}
    assert client.get(path, headers=bob).status_code == 200
    assert client.get(path, headers=bob).json()["permissions"]["can_write"] is False
    owner = client.get(path)
    assert owner.status_code == 200
    assert owner.json()["permissions"]["can_write"] is True
    assert owner.json()["permissions"]["can_share"] is True
    revoked = client.put(access_path, params={"recipient_type": "user"}, headers={"If-Match": shared.headers["etag"]}, json={"grants": []})
    assert revoked.status_code == 200
    assert client.get(path, headers=bob).status_code == 403
    assert client.get(path).json() == owner.json()
