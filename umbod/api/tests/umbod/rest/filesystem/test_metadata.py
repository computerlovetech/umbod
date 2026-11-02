from pathlib import Path
from uuid import uuid4

import pytest

from .conftest import FilesystemHttp
from .test_content import upload_file
from .test_http_contract import BASE


@pytest.fixture(params=["file", "directory"])
def described_node(filesystem_http: FilesystemHttp, request: pytest.FixtureRequest) -> dict[str, object]:
    client = filesystem_http.client
    root = client.get(f"{BASE}/browse").json()["node"]["id"]
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
    root = client.get(f"{BASE}/browse").json()["node"]["id"]
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
    root = client.get(f"{BASE}/browse").json()["node"]
    patch = {"parent_id": root["id"]} if "parent_id" in change else change
    response = client.patch(f"{BASE}/nodes/{root['id']}", json=patch, headers={"If-Match": f'"{root["revision"]}"'})
    assert response.status_code == 409
    assert client.get(f"{BASE}/browse").json()["node"] == root


def test_patch_returns_success_snapshot_despite_grant_revocation_after_commit(
    filesystem_http: FilesystemHttp, described_node: dict[str, object],
) -> None:
    from uuid import UUID

    from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
    from umbod.core.filesystem.authorization import VerifiedIdentityResolver
    from umbod.core.filesystem.updates import FilesystemNodeUpdates, NodeUpdateService
    from umbod.infrastructure import create_access_control_driver, create_filesystem_transactions
    from umbod.rest.filesystem.deps import get_filesystem_updates
    from tests.support.filesystem.access_snapshots import RevokeAfterCommitTransactions

    database = filesystem_http.factories.persistence_runtime.database
    node_id = UUID(str(described_node["id"]))
    principal = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    policies = create_access_control_driver(database=database)
    filesystem_http.client.portal.call(policies.add_grant, AccessGrant(
        node_id=node_id, principal=principal, permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False,
    ))
    updates = NodeUpdateService(VerifiedIdentityResolver(), RevokeAfterCommitTransactions(
        create_filesystem_transactions(database=database), policies, node_id, principal,
    ))

    def provide_updates() -> FilesystemNodeUpdates:
        return updates

    filesystem_http.app.dependency_overrides[get_filesystem_updates] = provide_updates
    path = f"{BASE}/nodes/{node_id}"
    response = filesystem_http.client.patch(
        path, json={"name": "committed"},
        headers={"Authorization": "Bearer bob", "If-Match": f'"{described_node["revision"]}"'},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "committed"
    assert response.json()["revision"] == described_node["revision"] + 1
    assert response.json()["permissions"]["can_write"] is True
    assert response.json()["visible_to"] == {"type": "restricted"}
    assert response.headers["etag"] == f'"{described_node["revision"] + 1}"'
    assert filesystem_http.client.get(path, headers={"Authorization": "Bearer bob"}).status_code == 403


def test_owner_patch_with_sqlite_corrupt_policy_returns_committed_unavailable_snapshot(
    filesystem_http: FilesystemHttp, tmp_path: Path,
) -> None:
    from uuid import UUID

    from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
    from umbod.infrastructure import create_access_control_driver
    from tests.support.filesystem.access_snapshots import corrupt_stored_grant

    client = filesystem_http.client
    home = client.post(BASE + "/home").json()
    grant = AccessGrant(
        node_id=UUID(home["id"]), principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False,
    )
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    client.portal.call(policies.add_grant, grant)
    corrupt_stored_grant(tmp_path / "filesystem.sqlite", grant)
    path = f"{BASE}/nodes/{home['id']}"
    inspected = client.get(path)
    assert inspected.status_code == 200
    assert inspected.json()["visible_to"] == {"type": "unavailable"}
    response = client.patch(path, json={"name": "renamed"}, headers={"If-Match": f'"{home["revision"]}"'})
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"
    assert response.json()["revision"] == home["revision"] + 1
    assert response.json()["permissions"]["can_write"] is True
    assert response.json()["permissions"]["can_share"] is True
    assert response.json()["visible_to"] == {"type": "unavailable"}
    assert client.get(path).json() == response.json()
