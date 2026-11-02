from typing import NoReturn
from uuid import uuid4

import pytest

from umbod.rest.filesystem.deps import get_filesystem_database

from .conftest import FilesystemHttp
from .test_http_contract import BASE


def forbid_database() -> NoReturn:
    pytest.fail("Removed routes must not resolve filesystem storage")


@pytest.mark.parametrize("method,path,status", [
    ("GET", "/nodes?scope=owned", 404),
    ("GET", "/nodes?scope=shared", 404),
    ("PUT", "/nodes/{id}/content", 405),
    ("PATCH", "/nodes/{id}/description", 404),
    ("OPTIONS", "/nodes/{id}/description", 404),
])
def test_removed_routes_do_not_access_storage(
    filesystem_http: FilesystemHttp, method: str, path: str, status: int,
) -> None:
    filesystem_http.app.dependency_overrides[get_filesystem_database] = forbid_database
    response = filesystem_http.client.request(method, BASE + path.format(id=uuid4()))
    assert response.status_code == status


def test_openapi_exposes_implemented_metadata_and_no_placeholders(filesystem_http: FilesystemHttp) -> None:
    paths = filesystem_http.client.get("/api/me/openapi.json").json()["paths"]
    assert "/filesystem/nodes" not in paths
    assert "/filesystem/nodes/{node_id}/description" not in paths
    content = paths["/filesystem/nodes/{node_id}/content"]
    assert "get" in content and "put" not in content
    patch = paths["/filesystem/nodes/{node_id}"]["patch"]
    assert {"200", "403", "412", "422", "428"} <= set(patch["responses"])
    assert any(p["name"] == "If-Match" and p["required"] for p in patch["parameters"])
    assert all("x-umbod-status" not in operation for methods in paths.values() for operation in methods.values())
    for method in ("get", "put"):
        assert "200" in paths["/filesystem/nodes/{node_id}/access"][method]["responses"]
    assert "201" in paths["/filesystem/nodes/{parent_id}/uploads"]["post"]["responses"]
    assert {"200", "307"} <= set(content["get"]["responses"])
    assert paths["/filesystem/nodes/{parent_id}/children"]["get"]["parameters"] == [{
        "name": "parent_id", "in": "path", "required": True,
        "schema": {"type": "string", "format": "uuid", "title": "Parent Id"},
    }]
