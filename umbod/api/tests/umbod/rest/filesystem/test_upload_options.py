from uuid import UUID, uuid4

import pytest

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.infrastructure import create_access_control_driver
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.filesystem.deps import get_filesystem_content_driver

from .conftest import FilesystemHttp
from .test_content import RecordingContentDriver, upload_file
from .test_http_contract import BASE, BODY


@pytest.fixture
def upload_parent(filesystem_http: FilesystemHttp) -> str:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    response = client.post(f"{BASE}/nodes/{root_id}/directories", json=BODY)
    assert response.status_code == 201
    return response.json()["id"]


def options_path(parent_id: str) -> str:
    return f"{BASE}/nodes/{parent_id}/uploads"


@pytest.mark.parametrize("filesystem_upload_max_bytes", [37], indirect=True)
def test_upload_options_return_allow_without_mutations_or_content_io(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    client = filesystem_http.client
    driver = RecordingContentDriver()

    def provide_driver() -> RecordingContentDriver:
        return driver

    filesystem_http.app.dependency_overrides[get_filesystem_content_driver] = provide_driver
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    parent_id = UUID(upload_parent)
    owner_before = client.portal.call(policies.get_owner, parent_id)
    grants_before = client.portal.call(policies.list_grants, parent_id)
    parent_before = client.get(f"{BASE}/nodes/{upload_parent}").json()
    children_before = client.get(f"{BASE}/nodes/{upload_parent}/children").json()

    response = client.options(options_path(upload_parent))

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["allow"] == "POST, OPTIONS"
    assert not any(key.startswith("x-umbod") for key in response.headers)
    assert response.headers["cache-control"] == "no-store"
    assert driver.uploads == driver.downloads == 0
    assert client.get(f"{BASE}/nodes/{upload_parent}").json() == parent_before
    assert client.get(f"{BASE}/nodes/{upload_parent}/children").json() == children_before
    assert client.portal.call(policies.get_owner, parent_id) == owner_before
    assert client.portal.call(policies.list_grants, parent_id) == grants_before


def test_readable_directory_does_not_imply_upload_eligibility(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    client = filesystem_http.client
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    client.portal.call(policies.add_grant, AccessGrant(
        node_id=UUID(upload_parent),
        principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions={Permission.DISCOVER, Permission.READ}, recursive=False,
    ))
    bob = {"Authorization": "Bearer bob"}
    assert client.get(f"{BASE}/nodes/{upload_parent}", headers=bob).status_code == 200
    response = client.options(options_path(upload_parent), headers=bob)
    missing = client.options(options_path(str(uuid4())), headers=bob)
    assert response.status_code == missing.status_code == 403
    assert response.json() == missing.json()
    assert response.json()["detail"]["code"] == "filesystem_permission_denied"


def test_private_and_missing_upload_options_are_indistinguishable(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    bob = {"Authorization": "Bearer bob"}
    private = filesystem_http.client.options(options_path(upload_parent), headers=bob)
    missing = filesystem_http.client.options(options_path(str(uuid4())), headers=bob)
    assert private.status_code == missing.status_code == 403
    assert private.json() == missing.json()
    assert private.json()["detail"]["code"] == "filesystem_permission_denied"


def test_file_parent_upload_options_returns_wrong_node_kind(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    uploaded = upload_file(filesystem_http.client, f"{BASE}/nodes/{upload_parent}/uploads", "file.bin", b"payload")
    assert uploaded.status_code == 201
    response = filesystem_http.client.options(options_path(uploaded.json()["id"]))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "filesystem_wrong_node_kind"


def test_unverified_upload_options_matches_missing_denial(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    client = filesystem_http.client
    missing = client.options(options_path(str(uuid4())))
    del filesystem_http.app.dependency_overrides[get_caller_context]
    response = client.options(options_path(upload_parent))
    assert response.status_code == missing.status_code == 403
    assert response.json() == missing.json()


def test_anonymous_upload_options_requires_authentication(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    response = filesystem_http.client.options(options_path(upload_parent), headers={"Authorization": ""})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_upload_options_invalid_uuid_returns_framework_validation(
    filesystem_http: FilesystemHttp,
) -> None:
    response = filesystem_http.client.options(options_path("not-a-uuid"))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


