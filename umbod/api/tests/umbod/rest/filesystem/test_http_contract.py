from uuid import uuid4

import pytest

from umbod.rest.authentication.deps import get_caller_context

from .conftest import FilesystemHttp

BASE = "/api/me/filesystem"
METADATA = {"content_type": {}, "attributes": {"label": "safe"}}
BODY = {"name": "child", "metadata": METADATA}


@pytest.mark.parametrize("kind", ["files", "directories"])
def test_group_root_creation_and_private_children(filesystem_http: FilesystemHttp, kind: str) -> None:
    client = filesystem_http.client
    root = client.get(f"{BASE}/root").json()
    response = client.post(f"{BASE}/nodes/{root['id']}/{kind}", json=BODY)
    assert response.status_code == 201
    child = response.json()
    assert child["kind"] == ("file" if kind == "files" else "directory")
    assert set(child) == {"id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision"}
    assert child["metadata"] == METADATA
    assert client.get(f"{BASE}/nodes/{child['id']}").json() == child
    assert client.get(f"{BASE}/nodes/{root['id']}/children").json() == {"nodes": [child]}
    bob = {"Authorization": "Bearer bob"}
    assert client.get(f"{BASE}/root", headers=bob).status_code == 200
    assert client.get(f"{BASE}/nodes/{root['id']}/children", headers=bob).json() == {"nodes": []}
    denied = client.get(f"{BASE}/nodes/{child['id']}", headers=bob)
    missing = client.get(f"{BASE}/nodes/{uuid4()}", headers=bob)
    assert denied.status_code == missing.status_code == 403
    assert denied.json() == missing.json()
    assert response.headers["cache-control"] == "no-store"
    assert "content" not in child and "key" not in child


@pytest.mark.parametrize("suffix,method", [
    ("/root", "GET"), ("/nodes/{id}", "GET"),
    ("/nodes/{id}/children", "GET"),
    ("/nodes/{id}/files", "POST"), ("/nodes/{id}/directories", "POST"),
])
def test_all_paths_deny_untrusted_or_ungranted_callers(
    filesystem_http: FilesystemHttp, suffix: str, method: str,
) -> None:
    client = filesystem_http.client
    identifier = client.get(f"{BASE}/root").json()["id"]
    path = BASE + suffix.format(id=identifier)
    outsider = client.request(method, path, json=BODY, headers={"Authorization": "Bearer outsider"})
    assert outsider.status_code == 403
    del filesystem_http.app.dependency_overrides[get_caller_context]
    untrusted = client.request(method, path, json=BODY)
    assert untrusted.status_code == 403
    assert untrusted.json() == outsider.json()
    unauthenticated = client.request(method, path, json=BODY, headers={"Authorization": ""})
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("kind", ["files", "directories"])
@pytest.mark.parametrize("body", [
    {}, {"name": "child"}, {"metadata": METADATA},
    {"name": 12, "metadata": METADATA}, {"name": "child", "metadata": None},
    {**BODY, "owner": "mallory"}, {**BODY, "grants": []},
    {**BODY, "caller": {}}, {**BODY, "content": {"key": "secret"}},
])
def test_creation_rejects_invalid_or_authority_injecting_bodies(
    filesystem_http: FilesystemHttp, kind: str, body: dict[str, object],
) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    response = client.post(f"{BASE}/nodes/{root_id}/{kind}", json=body)
    assert response.status_code == 422
    assert client.get(f"{BASE}/nodes/{root_id}/children").json() == {"nodes": []}


@pytest.mark.parametrize("kind", ["files", "directories"])
@pytest.mark.parametrize("field", ["owner", "content", "caller", "grants", "unexpected"])
def test_creation_rejects_nested_metadata_extras(
    filesystem_http: FilesystemHttp, kind: str, field: str,
) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    response = client.post(f"{BASE}/nodes/{root_id}/{kind}", json={
        **BODY, "metadata": {**METADATA, field: "injected"},
    })
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "metadata", field]
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
    assert client.get(f"{BASE}/nodes/{root_id}/children").json() == {"nodes": []}


@pytest.mark.parametrize("kind", ["files", "directories"])
def test_metadata_attributes_remain_arbitrary_data(
    filesystem_http: FilesystemHttp, kind: str,
) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    attributes = {"owner": "not-an-owner", "content": "not-content", "caller": "not-a-caller"}
    response = client.post(f"{BASE}/nodes/{root_id}/{kind}", json={
        **BODY, "metadata": {**METADATA, "attributes": attributes},
    })
    assert response.status_code == 201
    assert response.json()["metadata"]["attributes"] == attributes
    bob = client.get(
        f"{BASE}/nodes/{response.json()['id']}", headers={"Authorization": "Bearer bob"},
    )
    assert bob.status_code == 403


@pytest.mark.parametrize("suffix,method", [
    ("/nodes/not-a-uuid", "GET"), ("/nodes/not-a-uuid/children", "GET"),
    ("/nodes/not-a-uuid/files", "POST"), ("/nodes/not-a-uuid/directories", "POST"),
])
def test_invalid_uuid_is_framework_validation(
    filesystem_http: FilesystemHttp, suffix: str, method: str,
) -> None:
    response = filesystem_http.client.request(method, BASE + suffix, json=BODY)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_creation_domain_errors_and_cookie_csrf(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    path = f"{BASE}/nodes/{root_id}/files"
    blocked = client.post(path, json=BODY, headers={"Cookie": "session=present"})
    assert blocked.status_code == 403
    assert client.get(f"{BASE}/nodes/{root_id}/children").json() == {"nodes": []}
    allowed = client.post(path, json=BODY, headers={
        "Cookie": "session=present",
        "Origin": str(filesystem_http.factories.settings.endpoints.site_base_url).rstrip("/"),
        "X-Umbod-Web-Request": "1",
    })
    assert allowed.status_code == 201
    collision = client.post(path, json=BODY)
    assert collision.status_code == 409
    assert collision.json()["detail"]["code"] == "filesystem_name_collision"
    invalid = client.post(path, json={**BODY, "name": "a/b"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "filesystem_invalid_name"
    wrong = client.post(f"{BASE}/nodes/{allowed.json()['id']}/directories", json=BODY)
    assert wrong.status_code == 409
    assert wrong.json()["detail"]["code"] == "filesystem_wrong_node_kind"
