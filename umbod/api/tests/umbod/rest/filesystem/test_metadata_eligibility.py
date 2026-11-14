from typing import Literal
from uuid import UUID, uuid4

import pytest

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.errors import StorageFailure
from umbod.rest.filesystem.deps import get_filesystem_deletion, get_filesystem_updates

from .conftest import FilesystemHttp
from .test_content import upload_file
from .test_http_contract import BASE


@pytest.fixture(params=["file", "directory"])
def editable_node(filesystem_http: FilesystemHttp, request: pytest.FixtureRequest) -> dict[str, object]:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/browse").json()["node"]["id"]
    if request.param == "file":
        response = upload_file(client, f"{BASE}/nodes/{root_id}/uploads", "file", b"bytes")
    else:
        response = client.post(f"{BASE}/nodes/{root_id}/directories", json={
            "name": "folder", "metadata": {"content_type": {}, "attributes": {}},
        })
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("access,methods", [
    ("read", {"GET", "OPTIONS"}),
    ("read_write", {"GET", "OPTIONS", "PATCH", "DELETE"}),
])
def test_options_reports_shared_namespace_access(
    filesystem_http: FilesystemHttp, access: Literal["read", "read_write"], methods: set[str],
) -> None:
    from .conftest import create_shared_namespace, replace_shared_access

    namespace = create_shared_namespace(filesystem_http, "read_write")
    client = filesystem_http.client
    node = upload_file(client, f"{BASE}/nodes/{namespace.root_node_id}/uploads", "shared", b"bytes").json()
    replace_shared_access(filesystem_http, namespace, access)
    response = client.options(f"{BASE}/nodes/{node['id']}", headers={"Authorization": "Bearer bob"})
    assert response.status_code == 204
    assert set(response.headers["allow"].split(", ")) == methods
    assert response.headers["cache-control"] == "no-store"
    current = client.get(f"{BASE}/nodes/{node['id']}").json()
    assert current["visible_to"] == {
        "type": "namespace", "namespace_id": str(namespace.id), "kind": "shared", "name": namespace.name,
    }


def test_owner_options_includes_all_applicable_operations(
    filesystem_http: FilesystemHttp, editable_node: dict[str, object],
) -> None:
    response = filesystem_http.client.options(f"{BASE}/nodes/{editable_node['id']}")
    expected = {"GET", "OPTIONS", "PATCH"}
    if editable_node["kind"] == "file":
        expected.add("DELETE")
    assert response.status_code == 204
    assert set(response.headers["allow"].split(", ")) == expected


def test_options_inaccessible_and_missing_are_indistinguishable(
    filesystem_http: FilesystemHttp, editable_node: dict[str, object],
) -> None:
    client = filesystem_http.client
    responses = [client.options(f"{BASE}/nodes/{node_id}", headers={"Authorization": "Bearer bob"})
                 for node_id in (editable_node["id"], uuid4())]
    assert responses[0].status_code == responses[1].status_code == 403
    assert responses[0].json() == responses[1].json()


class FailingEligibility:
    async def check_update_eligibility(self, snapshot: CallerSnapshot, node_id: UUID) -> None:
        raise StorageFailure()

    async def check_delete_eligibility(self, snapshot: CallerSnapshot, node_id: UUID) -> None:
        raise StorageFailure()


@pytest.mark.parametrize("operation", ["metadata", "deletion"])
def test_options_does_not_mask_storage_failure(
    filesystem_http: FilesystemHttp, editable_node: dict[str, object], operation: str,
) -> None:
    provider = get_filesystem_updates if operation == "metadata" else get_filesystem_deletion
    filesystem_http.app.dependency_overrides[provider] = FailingEligibility
    response = filesystem_http.client.options(f"{BASE}/nodes/{editable_node['id']}")
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "filesystem_storage_failure"
