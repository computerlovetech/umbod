from uuid import UUID, uuid4

import pytest

from umbod.core.filesystem import AccessGrant, Ownership, Permission, Principal, PrincipalType
from umbod.infrastructure import create_access_control_driver
from .conftest import FilesystemHttp
from .test_content import upload_file
from .test_http_contract import BASE


def create_folder(http: FilesystemHttp, parent_id: str, name: str) -> dict[str, object]:
    response = http.client.post(f"{BASE}/nodes/{parent_id}/directories", json={
        "name": name, "metadata": {"content_type": {}, "attributes": {}},
    })
    assert response.status_code == 201
    return response.json()


def test_browse_openapi_describes_optional_uuid_target(filesystem_http: FilesystemHttp) -> None:
    schema = filesystem_http.client.get("/api/me/openapi.json").json()
    operation = schema["paths"]["/filesystem/browse"]["get"]
    assert operation["parameters"] == [{
        "name": "node_id", "in": "query", "required": False,
        "description": "Node to browse; omit to browse the filesystem root.",
        "schema": {"type": "string", "format": "uuid"},
    }]


def test_browse_omitted_target_returns_canonical_root_contract(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    root = client.get(f"{BASE}/browse").json()["node"]
    folder = create_folder(filesystem_http, root["id"], "folder")
    response = client.get(f"{BASE}/browse")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"node", "breadcrumbs", "entries", "capabilities", "truncated"}
    assert body["node"] == root
    assert body["entries"] == [folder]
    assert body["truncated"] is False
    assert body["breadcrumbs"] == {"items": [{"id": root["id"], "name": "", "kind": "directory"}], "complete": True}
    assert body["capabilities"][0] == {
        "node_id": root["id"], "rename": False, "move": False, "edit_description": True,
        "delete": False, "share": False, "upload": True, "create_directory": True,
    }


def test_browse_file_inspection_returns_no_entries_or_content(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    root = client.get(f"{BASE}/browse").json()["node"]["id"]
    uploaded = upload_file(client, f"{BASE}/nodes/{root}/uploads", "file", b"private file content")
    assert uploaded.status_code == 201
    node = uploaded.json()
    response = client.get(f"{BASE}/browse", params={"node_id": node["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["node"] == node
    assert body["entries"] == []
    assert body["capabilities"] == [{
        "node_id": node["id"], "rename": True, "move": True, "edit_description": True,
        "delete": True, "share": True, "upload": False, "create_directory": False,
    }]
    assert "private file content" not in response.text
    assert "content" not in body["node"]


@pytest.mark.parametrize("raw", ["", "not-a-uuid", "null"])
def test_browse_rejects_invalid_query_uuid(filesystem_http: FilesystemHttp, raw: str) -> None:
    response = filesystem_http.client.get(f"{BASE}/browse", params={"node_id": raw})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "node_id"]


def test_browse_missing_and_denied_targets_are_indistinguishable(filesystem_http: FilesystemHttp) -> None:
    root = filesystem_http.client.get(f"{BASE}/browse").json()["node"]["id"]
    target = create_folder(filesystem_http, root, "private")
    responses = [filesystem_http.client.get(f"{BASE}/browse", params={"node_id": node_id},
                headers={"Authorization": "Bearer outsider"}) for node_id in (target["id"], str(uuid4()))]
    assert responses[0].status_code == responses[1].status_code == 403
    assert responses[0].json() == responses[1].json()


def test_mutation_rechecks_revoked_write_after_browse_projection(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    root = client.get(f"{BASE}/browse").json()["node"]["id"]
    target = create_folder(filesystem_http, root, "target")
    initial = client.get(f"{BASE}/browse", params={"node_id": target["id"]}).json()
    assert initial["capabilities"][0]["rename"] is True
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    node_id = UUID(target["id"])
    client.portal.call(policies.set_owner, Ownership(
        node_id=node_id, owner=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
    ))
    client.portal.call(policies.add_grant, AccessGrant(
        node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"),
        permissions={Permission.DISCOVER}, recursive=False,
    ))
    patch = client.patch(f"{BASE}/nodes/{node_id}", json={"name": "forbidden"},
                         headers={"If-Match": f'"{target["revision"]}"'})
    assert patch.status_code == 403
    refreshed = client.get(f"{BASE}/browse", params={"node_id": target["id"]}).json()
    assert refreshed["capabilities"][0]["rename"] is False
    assert refreshed["node"]["name"] == "target"
