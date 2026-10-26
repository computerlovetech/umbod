from typing import NoReturn
from uuid import uuid4

import pytest
from starlette.requests import Request

from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.filesystem.deps import get_filesystem_database

from .conftest import FilesystemHttp
from .test_http_contract import BASE, BODY

REVISION = {"If-Match": '"1"'}
OPERATIONS = [
    ("GET", "/nodes?scope=owned", {}),
    ("GET", "/nodes?scope=shared", {}),
    ("GET", "/nodes/{id}/breadcrumbs", {}),
    ("GET", "/nodes/{id}/content", {}),
    ("PUT", "/nodes/{id}/content", {}),
    ("PATCH", "/nodes/{id}", {"name": "renamed"}),
    ("DELETE", "/nodes/{id}", {}),
    ("GET", "/nodes/{id}/access", {}),
    ("PUT", "/nodes/{id}/access", {"grants": []}),
]
DETAIL = {
    "code": "filesystem_not_implemented",
    "message": "Filesystem operation is not implemented.",
}


def forbid_database() -> NoReturn:
    pytest.fail("Placeholder accessed persistence.")


@pytest.mark.parametrize("method,path,body", OPERATIONS)
def test_planned_operations_do_not_lookup_or_mutate(
    filesystem_http: FilesystemHttp, method: str, path: str, body: dict[str, object],
) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    child = client.post(f"{BASE}/nodes/{root_id}/files", json=BODY).json()
    before = client.get(f"{BASE}/nodes/{root_id}/children").json()
    filesystem_http.app.dependency_overrides[get_filesystem_database] = forbid_database
    for identifier in (root_id, child["id"], str(uuid4())):
        response = client.request(
            method, BASE + path.format(id=identifier), json=body, headers=REVISION,
        )
        assert response.status_code == 501
        assert response.json() == {"detail": DETAIL}
        assert response.headers["cache-control"] == "no-store"
        denied_item = client.request(
            method, BASE + path.format(id=identifier), json=body,
            headers={**REVISION, "Authorization": "Bearer bob"},
        )
        assert denied_item.status_code == 501
        assert denied_item.json() == response.json()
    del filesystem_http.app.dependency_overrides[get_filesystem_database]
    assert client.get(f"{BASE}/nodes/{root_id}/children").json() == before
    assert client.get(f"{BASE}/nodes/{child['id']}").json() == child


@pytest.mark.parametrize("method,path,body", OPERATIONS)
def test_planned_operations_require_authentication_and_verified_identity(
    filesystem_http: FilesystemHttp, method: str, path: str, body: dict[str, object],
) -> None:
    path = BASE + path.format(id=uuid4())
    client = filesystem_http.client
    anonymous = client.request(method, path, json=body, headers={**REVISION, "Authorization": ""})
    assert anonymous.status_code == 401
    del filesystem_http.app.dependency_overrides[get_caller_context]
    denied = client.request(method, path, json=body, headers=REVISION)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "filesystem_permission_denied"
    assert denied.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("method,path,body", [item for item in OPERATIONS if item[0] != "GET"])
def test_planned_mutations_keep_cookie_csrf(
    filesystem_http: FilesystemHttp, method: str, path: str, body: dict[str, object],
) -> None:
    path = BASE + path.format(id=uuid4())
    headers = {**REVISION, "Cookie": "session=present"}
    blocked = filesystem_http.client.request(method, path, json=body, headers=headers)
    assert blocked.status_code == 403
    allowed = filesystem_http.client.request(method, path, json=body, headers={
        **headers,
        "Origin": str(filesystem_http.factories.settings.endpoints.site_base_url).rstrip("/"),
        "X-Umbod-Web-Request": "1",
    })
    assert allowed.status_code == 501


@pytest.mark.parametrize("method,path,body,headers", [
    ("GET", "/nodes", {}, {}),
    ("GET", "/nodes?scope=all", {}, {}),
    ("GET", "/nodes/not-a-uuid/breadcrumbs", {}, {}),
    ("GET", "/nodes/not-a-uuid/content", {}, {}),
    ("GET", "/nodes/not-a-uuid/access", {}, {}),
    ("PUT", "/nodes/not-a-uuid/content", {}, REVISION),
    ("PATCH", "/nodes/not-a-uuid", {"name": "new"}, REVISION),
    ("DELETE", "/nodes/not-a-uuid", {}, REVISION),
    ("PUT", "/nodes/not-a-uuid/access", {"grants": []}, REVISION),
    ("PATCH", "/nodes/{id}", {}, REVISION),
    ("PATCH", "/nodes/{id}", {"name": None}, REVISION),
    ("PATCH", "/nodes/{id}", {"name": 12}, REVISION),
    ("PATCH", "/nodes/{id}", {"metadata": {}}, REVISION),
    ("PATCH", "/nodes/{id}", {"parent_id": None}, REVISION),
    ("PATCH", "/nodes/{id}", {"parent_id": "not-a-uuid"}, REVISION),
    ("PATCH", "/nodes/{id}", {"owner": "mallory"}, REVISION),
    ("PATCH", "/nodes/{id}", {"grants": []}, REVISION),
    ("PUT", "/nodes/{id}/access", {"owner": "mallory", "grants": []}, REVISION),
    ("PUT", "/nodes/{id}/access", {"grants": [{"principal": {
        "type": "system", "issuer": "umbod:system", "id": "root",
    }, "permissions": ["write"]}]}, REVISION),
    ("PATCH", "/nodes/{id}", {"name": "new"}, {}),
    ("DELETE", "/nodes/{id}", {}, {"If-Match": "*"}),
    ("PUT", "/nodes/{id}/content", {}, {}),
    ("PUT", "/nodes/{id}/access", {"grants": []}, {}),
])
def test_planned_requests_validate_contract(
    filesystem_http: FilesystemHttp, method: str, path: str,
    body: dict[str, object], headers: dict[str, str],
) -> None:
    response = filesystem_http.client.request(
        method, BASE + path.format(id=uuid4()), json=body, headers=headers,
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_multipart_rejected_before_body_or_storage(
    filesystem_http: FilesystemHttp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbid_read(self: Request) -> NoReturn:
        pytest.fail("Upload body was read.")

    filesystem_http.app.dependency_overrides[get_filesystem_database] = forbid_database
    monkeypatch.setattr(Request, "body", forbid_read)
    monkeypatch.setattr(Request, "form", forbid_read)
    response = filesystem_http.client.post(
        f"{BASE}/nodes/{uuid4()}/files", content=b"not even valid multipart",
        headers={"Content-Type": "multipart/form-data; boundary=ignored"},
    )
    assert response.status_code == 501
    assert response.json() == {"detail": DETAIL}
    assert response.headers["cache-control"] == "no-store"
    del filesystem_http.app.dependency_overrides[get_caller_context]
    denied = filesystem_http.client.post(
        f"{BASE}/nodes/{uuid4()}/files", content=b"ignored",
        headers={"Content-Type": "multipart/form-data; boundary=ignored"},
    )
    assert denied.status_code == 403


@pytest.mark.parametrize("content_type,content,location", [
    ("text/plain", b"{}", ["body"]),
    ("application/json", b"invalid json", ["body"]),
    ("application/json", b'{"name":"child","metadata":{},"owner":"mallory"}', ["body", "owner"]),
])
def test_file_creation_invalid_input_preserves_body_validation(
    filesystem_http: FilesystemHttp, content_type: str, content: bytes, location: list[str],
) -> None:
    response = filesystem_http.client.post(
        f"{BASE}/nodes/{uuid4()}/files", content=content, headers={"Content-Type": content_type},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == location


def test_openapi_indexes_planned_and_legacy_contracts(filesystem_http: FilesystemHttp) -> None:
    schema = filesystem_http.client.get("/api/me/openapi.json").json()
    paths = schema["paths"]
    for method, path, _ in OPERATIONS:
        operation = paths[("/filesystem" + path.split("?")[0]).replace("{id}", "{node_id}")][method.lower()]
        assert operation["x-umbod-status"] == "planned"
        assert "501" in operation["responses"]
        assert "200" not in operation["responses"]
        if method in ("PUT", "PATCH", "DELETE"):
            assert any(p["name"] == "If-Match" and p["required"] for p in operation["parameters"])
    upload = paths["/filesystem/nodes/{parent_id}/files"]["post"]
    assert set(upload["requestBody"]["content"]) == {"application/json", "multipart/form-data"}
    assert upload["x-umbod-multipart-status"] == "planned"
    assert upload["requestBody"]["content"]["multipart/form-data"]["schema"]["required"] == ["file"]
    assert "201" in upload["responses"] and "501" in upload["responses"]
    assert paths["/filesystem/nodes/{parent_id}/children"]["get"]["parameters"] == [{
        "name": "parent_id", "in": "path", "required": True,
        "schema": {"type": "string", "format": "uuid", "title": "Parent Id"},
    }]
