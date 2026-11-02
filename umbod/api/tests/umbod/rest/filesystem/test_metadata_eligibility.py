from uuid import UUID, uuid4

import pytest

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.errors import StorageFailure
from umbod.infrastructure import create_access_control_driver
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


@pytest.mark.parametrize("permissions,methods", [
    ({Permission.DISCOVER}, {"GET", "OPTIONS"}),
    ({Permission.DISCOVER, Permission.WRITE}, {"GET", "OPTIONS", "PATCH"}),
    ({Permission.DISCOVER, Permission.DELETE}, {"GET", "OPTIONS", "DELETE"}),
    ({Permission.DISCOVER, Permission.WRITE, Permission.DELETE}, {"GET", "OPTIONS", "PATCH", "DELETE"}),
])
def test_options_reports_each_operation_independently(
    filesystem_http: FilesystemHttp, editable_node: dict[str, object],
    permissions: set[Permission], methods: set[str],
) -> None:
    client = filesystem_http.client
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    node_id = UUID(str(editable_node["id"]))
    client.portal.call(policies.add_grant, AccessGrant(
        node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions=permissions, recursive=False,
    ))
    response = client.options(f"{BASE}/nodes/{node_id}", headers={"Authorization": "Bearer bob"})
    assert response.status_code == 204
    expected = methods - {"DELETE"} if editable_node["kind"] == "directory" else methods
    assert set(response.headers["allow"].split(", ")) == expected
    assert response.headers["cache-control"] == "no-store"
    current = client.get(f"{BASE}/nodes/{node_id}").json()
    assert {key: value for key, value in current.items() if key != "visible_to"} == {key: value for key, value in editable_node.items() if key != "visible_to"}
    assert set(current["visible_to"]["grants"][0]["permissions"]) == {permission.value for permission in permissions}


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
