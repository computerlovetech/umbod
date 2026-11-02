from uuid import uuid4

import pytest

from .conftest import FilesystemHttp
from .test_content import upload_file
from .test_http_contract import BASE


@pytest.fixture(params=["file", "directory"])
def described_node(filesystem_http: FilesystemHttp, request: pytest.FixtureRequest) -> dict[str, object]:
    client = filesystem_http.client
    root = client.get(f"{BASE}/root").json()["id"]
    if request.param == "file":
        response = upload_file(client, f"{BASE}/nodes/{root}/uploads", "file", b"bytes")
    else:
        response = client.post(f"{BASE}/nodes/{root}/directories", json={
            "name": "folder", "metadata": {"content_type": "text/plain", "attributes": {"description": "Initial", "team": "research"}},
        })
    assert response.status_code == 201
    return response.json()


def test_description_options_update_clear_and_stale_revision(filesystem_http: FilesystemHttp, described_node: dict[str, object]) -> None:
    client = filesystem_http.client
    path = f"{BASE}/nodes/{described_node['id']}"
    options = client.options(f"{path}")
    assert options.status_code == 204
    assert {"GET", "OPTIONS", "PATCH"} <= set(options.headers["allow"].split(", "))
    assert options.headers["cache-control"] == "no-store"
    headers = {"If-Match": f'"{described_node["revision"]}"'}
    updated = client.patch(f"{path}", json={"metadata": {"attributes": {"description": "What is here\nwhen to read"}}}, headers=headers)
    assert updated.status_code == 200
    node = updated.json()
    assert node["metadata"]["attributes"]["description"] == "What is here\nwhen to read"
    assert node["revision"] == described_node["revision"] + 1
    assert updated.headers["etag"] == f'"{node["revision"]}"'
    assert updated.headers["cache-control"] == "no-store"
    assert client.get(path).json() == node
    assert client.patch(f"{path}", json={"metadata": {"attributes": {"description": "stale"}}}, headers=headers).status_code == 412
    cleared = client.patch(f"{path}", json={"metadata": {"attributes": {"description": ""}}}, headers={"If-Match": updated.headers["etag"]})
    assert cleared.status_code == 200
    assert "description" not in cleared.json()["metadata"]["attributes"]
    for key in ("name", "created_at", "kind", "parent_id"):
        assert cleared.json()[key] == described_node[key]
    assert cleared.json()["metadata"]["content_type"] == described_node["metadata"]["content_type"]


@pytest.mark.parametrize("content_type", ["application/json", {}])
def test_generic_metadata_patch_merges_attributes_and_replaces_content_type(
    filesystem_http: FilesystemHttp, described_node: dict[str, object], content_type: object,
) -> None:
    client = filesystem_http.client
    path = f"{BASE}/nodes/{described_node['id']}"
    attributes = described_node["metadata"]["attributes"]
    response = client.patch(path, json={"metadata": {
        "attributes": {"tag": ""}, "content_type": content_type,
    }}, headers={"If-Match": f'"{described_node["revision"]}"'})
    assert response.status_code == 200
    updated = response.json()
    assert updated["metadata"] == {"attributes": {**attributes, "tag": ""}, "content_type": content_type}
    content_only = client.patch(path, json={"metadata": {"content_type": "text/plain"}},
                                headers={"If-Match": response.headers["etag"]})
    assert content_only.status_code == 200
    assert content_only.json()["metadata"]["attributes"] == updated["metadata"]["attributes"]
    for key in ("name", "parent_id", "created_at", "kind"):
        assert content_only.json()[key] == described_node[key]


@pytest.mark.parametrize("body", [{}, {"metadata": {}}, {"metadata": {"attributes": {}}}, {"metadata": {"attributes": None}}, {"metadata": {"content_type": None}}, {"metadata": {"attributes": {"x": 1}}}, {"metadata": {"name": "new"}}, {"metadata": {"parent_id": "new"}}, {"name": {}, "metadata": {"content_type": "text/plain"}}, {"parent_id": "new"}, {"metadata": {"extra": True}}])
def test_description_strict_body(filesystem_http: FilesystemHttp, described_node: dict[str, object], body: dict[str, object]) -> None:
    path = f"{BASE}/nodes/{described_node['id']}"
    response = filesystem_http.client.patch(path, json=body, headers={"If-Match": f'"{described_node["revision"]}"'})
    assert response.status_code == 422


@pytest.mark.parametrize("header,status", [(None, 428), ("*", 422), ('W/"1"', 422), ('"0"', 422), ('"1", "2"', 422)])
def test_description_preconditions(filesystem_http: FilesystemHttp, described_node: dict[str, object], header: str | None, status: int) -> None:
    path = f"{BASE}/nodes/{described_node['id']}"
    headers = {} if header is None else {"If-Match": header}
    assert filesystem_http.client.patch(path, json={"metadata": {"attributes": {"description": "x"}}}, headers=headers).status_code == status


def test_description_missing_and_unauthorized_match(filesystem_http: FilesystemHttp, described_node: dict[str, object]) -> None:
    client = filesystem_http.client
    for method in ("OPTIONS", "PATCH"):
        responses = [client.request(method, f"{BASE}/nodes/{node_id}", json={"metadata": {"attributes": {"description": "x"}}},
                                    headers={"Authorization": "Bearer bob", "If-Match": '"999"'})
                     for node_id in (described_node["id"], str(uuid4()))]
        assert responses[0].status_code == responses[1].status_code == 403
        assert responses[0].json() == responses[1].json()



def test_combined_rename_move_metadata_and_stale_request(
    filesystem_http: FilesystemHttp, described_node: dict[str, object],
) -> None:
    client = filesystem_http.client
    root = client.get(f"{BASE}/root").json()["id"]
    destination = client.post(f"{BASE}/nodes/{root}/directories", json={
        "name": "destination", "metadata": {"attributes": {}, "content_type": {}},
    }).json()
    path = f"{BASE}/nodes/{described_node['id']}"
    patch = {"name": "renamed", "parent_id": destination["id"], "metadata": {"attributes": {"tag": "release"}}}
    headers = {"If-Match": f'"{described_node["revision"]}"'}
    response = client.patch(path, json=patch, headers=headers)
    assert response.status_code == 200
    updated = response.json()
    assert (updated["name"], updated["parent_id"], updated["revision"]) == ("renamed", destination["id"], described_node["revision"] + 1)
    assert updated["metadata"]["attributes"]["tag"] == "release"
    stale = client.patch(path, json={"name": "stale", "parent_id": root}, headers=headers)
    assert stale.status_code == 412
    assert client.get(path).json() == updated
    denied = client.patch(path, json=patch, headers={"If-Match": response.headers["etag"], "Authorization": "Bearer bob"})
    assert denied.status_code == 403
    assert client.get(path).json() == updated



@pytest.mark.parametrize("change", [{"name": ""}, {"parent_id": None}])
def test_root_structural_patch_conflict(
    filesystem_http: FilesystemHttp, change: dict[str, object],
) -> None:
    client = filesystem_http.client
    root = client.get(f"{BASE}/root").json()
    patch = {"parent_id": root["id"]} if "parent_id" in change else change
    response = client.patch(f"{BASE}/nodes/{root['id']}", json=patch, headers={"If-Match": f'"{root["revision"]}"'})
    assert response.status_code == 409
    assert client.get(f"{BASE}/root").json() == root
