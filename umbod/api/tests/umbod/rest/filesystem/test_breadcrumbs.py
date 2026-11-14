from umbod.core.filesystem.namespace import ROOT_ID
from uuid import uuid4

import pytest

from umbod.rest.authentication.deps import get_caller_context

from .conftest import FilesystemHttp
from .test_http_contract import BASE, BODY, creation_payload


def test_breadcrumbs_return_minimal_ordered_items_and_no_store(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    browsed = client.get(f"{BASE}/browse")
    assert browsed.status_code == 200, browsed.text
    root = browsed.json()["node"]
    directory = client.post(f"{BASE}/nodes/{root['id']}/directories", **creation_payload("directories", BODY)).json()
    response = client.get(f"{BASE}/nodes/{directory['id']}/breadcrumbs")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [{key: node[key] for key in ("id", "name", "kind")} for node in (root, directory)],
        "complete": True,
    }
    assert client.get(f"{BASE}/nodes/{root['id']}/breadcrumbs").json() == {
        "items": [{"id": root["id"], "name": root["name"], "kind": "directory"}], "complete": True,
    }


def test_namespace_breadcrumbs_do_not_expose_structural_root(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    root = client.get(f"{BASE}/browse").json()["node"]
    response = client.get(f"{BASE}/nodes/{root['id']}/breadcrumbs")
    assert response.status_code == 200
    assert response.json() == {
        "items": [{key: root[key] for key in ("id", "name", "kind")}], "complete": True,
    }
    assert root["id"] != str(ROOT_ID)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("identifier", ["unknown", "hidden"])
def test_target_denial_is_fixed_and_no_store(filesystem_http: FilesystemHttp, identifier: str) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/browse").json()["node"]["id"]
    response = client.get(
        f"{BASE}/nodes/{uuid4() if identifier == 'unknown' else root_id}/breadcrumbs",
        headers={"Authorization": "Bearer outsider"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "filesystem_permission_denied", "message": "Filesystem access denied."}}
    assert response.headers["cache-control"] == "no-store"


def test_breadcrumbs_require_authentication_verified_identity_and_uuid(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    url = f"{BASE}/nodes/{uuid4()}/breadcrumbs"
    response = client.get(url, headers={"Authorization": ""})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    invalid = client.get(f"{BASE}/nodes/not-a-uuid/breadcrumbs")
    assert invalid.status_code == 422
    assert invalid.headers["cache-control"] == "no-store"
    del filesystem_http.app.dependency_overrides[get_caller_context]
    assert client.get(url).status_code == 403


def test_breadcrumbs_openapi_documents_live_minimal_response(filesystem_http: FilesystemHttp) -> None:
    schema = filesystem_http.client.get("/api/me/openapi.json").json()
    operation = schema["paths"]["/filesystem/nodes/{node_id}/breadcrumbs"]["get"]
    assert "200" in operation["responses"]
    assert "501" not in operation["responses"]
    assert "x-umbod-status" not in operation
    schemas = schema["components"]["schemas"]
    response = schemas["Breadcrumbs"]
    assert set(response["properties"]) == set(response["required"]) == {"items", "complete"}
    assert response["properties"]["items"]["minItems"] == 1
    assert set(schemas["BreadcrumbItem"]["properties"]) == {"id", "name", "kind"}
    assert schemas["NodeKind"]["enum"] == ["file", "directory"]
