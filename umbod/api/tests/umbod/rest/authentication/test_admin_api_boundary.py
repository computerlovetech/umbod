import json
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    availability = tmp_path / "availability.json"
    availability.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability))
    settings = APISettings(
        rest={"metrics_port": 19587},
        admin_authentication={
            "mode": "jwt",
            "environment": "development",
            "jwt_header_name": "Authorization",
        },
        endpoints={"site_base_url": "https://site.example.com"},
        cors={"origins": ["https://spa.example.com", "*"]},
    )
    with TestClient(create_app(settings, [])) as transport:
        yield transport


@pytest.fixture
def bearer_headers() -> dict[str, str]:
    token = json.dumps({
        "signature": "trusted",
        "claims": {
            "sub": "admin-123",
            "email": "admin@example.com",
            "name": "Admin",
            "groups": ["umbod-admins"],
        },
    })
    return {"Authorization": f"Bearer {token}"}


def test_canonical_api_returns_authenticated_identity(
    client: TestClient, bearer_headers: dict[str, str]
) -> None:
    response = client.get("/api/admin/users", headers=bearer_headers)
    assert response.status_code == 200
    assert response.json()["id"] == "admin-123"
    assert response.json()["email"] == "admin@example.com"


@pytest.mark.parametrize("route", ["/users", "/docs", "/openapi.json"])
@pytest.mark.parametrize("membership,status", [(None, 401), ("umbod-users", 403)])
def test_canonical_api_requires_admin_authentication(
    client: TestClient, route: str, membership: str | None, status: int
) -> None:
    headers = {} if membership is None else {
        "Authorization": "Bearer " + json.dumps({
            "signature": "trusted", "claims": {"groups": [membership]},
        }),
    }
    assert client.get(f"/api/admin{route}", headers=headers).status_code == status


def test_canonical_api_persists_authenticated_mutations(
    client: TestClient, bearer_headers: dict[str, str]
) -> None:
    response = client.post("/api/admin/mcp-permissions/groups/test-group", headers=bearer_headers)
    assert response.status_code == 200
    response = client.get("/api/admin/mcp-permissions/groups", headers=bearer_headers)
    assert response.status_code == 200
    assert response.json() == {"groups": [{"group_id": "test-group"}]}


def test_openapi_and_docs_use_canonical_mount_prefix(
    client: TestClient, bearer_headers: dict[str, str]
) -> None:
    response = client.get("/api/admin/openapi.json", headers=bearer_headers)
    assert response.status_code == 200
    assert response.json()["servers"] == [{"url": "/api/admin"}]
    assert "/users" in response.json()["paths"]
    docs = client.get("/api/admin/docs", headers=bearer_headers)
    assert docs.status_code == 200
    assert "/api/admin/openapi.json" in docs.text


@pytest.mark.parametrize("method,route", [
    ("GET", ""), ("GET", "/"),
    ("GET", "/users"), ("GET", "/docs"), ("GET", "/openapi.json"),
    ("POST", "/mcp-permissions/groups/legacy"),
    ("PUT", "/mcp-permissions/groups/legacy/permissions"),
    ("PATCH", "/connectors/openapi/legacy"),
    ("DELETE", "/mcp-permissions/groups/legacy"),
])
@pytest.mark.parametrize("authenticated", [False, True])
def test_legacy_api_returns_not_found_without_redirects(
    client: TestClient, bearer_headers: dict[str, str], method: str, route: str,
    authenticated: bool,
) -> None:
    headers = bearer_headers if authenticated else {}
    response = client.request(method, f"/admin{route}", headers=headers, follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers
    assert client.get("/api/admin/mcp-permissions/groups", headers=bearer_headers).json() == {"groups": []}


def test_system_alias_is_equivalent_and_public(client: TestClient) -> None:
    original = client.get("/system/health")
    alias = client.get("/api/system/health")
    assert original.status_code == alias.status_code == 200
    assert original.json() == alias.json()


@pytest.mark.parametrize("route", ["/events", "/connectors/runtime-state", "/mcp-permissions/groups", "/docs", "/openapi.json"])
def test_system_alias_does_not_expose_internal_routes(client: TestClient, route: str) -> None:
    assert client.get(f"/api/system{route}").status_code == 404


def test_openapi_respects_upstream_asgi_root_prefix(client: TestClient, bearer_headers: dict[str, str]) -> None:
    with closing(TestClient(client.app, root_path="/gateway")) as prefixed:
        response = prefixed.get("/gateway/api/admin/openapi.json", headers=bearer_headers)
        assert response.status_code == 200
        assert response.json()["servers"] == [{"url": "/gateway/api/admin"}]
        docs = prefixed.get("/gateway/api/admin/docs", headers=bearer_headers)
        assert "/gateway/api/admin/openapi.json" in docs.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("origin,marker", [
    (None, None), (None, "1"), ("https://site.example.com", None),
    ("https://site.example.com", "0"), ("https://attacker.example.com", "1"),
    ("null", "1"), ("*", "1"), ("https://site.example.com.attacker.example.com", "1"),
])
def test_cookie_mutations_reject_untrusted_requests_before_execution(
    client: TestClient, bearer_headers: dict[str, str],
    method: str, origin: str | None, marker: str | None,
) -> None:
    headers = {**bearer_headers, "Cookie": "gateway=session"}
    if origin is not None:
        headers["Origin"] = origin
    if marker is not None:
        headers["X-Umbod-Web-Request"] = marker
    response = client.request(method, "/api/admin/mcp-permissions/groups/blocked", headers=headers)
    assert response.status_code == 403
    assert client.get("/api/admin/mcp-permissions/groups", headers=bearer_headers).json() == {"groups": []}


@pytest.mark.parametrize("origin", ["https://site.example.com", "https://spa.example.com"])
def test_cookie_mutation_accepts_explicit_origin_and_marker(
    client: TestClient, bearer_headers: dict[str, str], origin: str
) -> None:
    headers = {**bearer_headers, "Cookie": "gateway=session", "Origin": origin, "X-Umbod-Web-Request": "1"}
    assert client.post("/api/admin/mcp-permissions/groups/allowed", headers=headers).status_code == 200


@pytest.mark.parametrize("method,route", [("GET", "/users"), ("HEAD", "/openapi.json"), ("OPTIONS", "/users")])
def test_cookie_safe_methods_do_not_require_origin_or_marker(
    client: TestClient, bearer_headers: dict[str, str], method: str, route: str
) -> None:
    response = client.request(method, f"/api/admin{route}", headers={**bearer_headers, "Cookie": "gateway=session"})
    assert response.status_code != 403


def test_cross_origin_bearer_preflight_keeps_credentials_disabled(client: TestClient) -> None:
    response = client.options("/api/admin/users", headers={
        "Origin": "https://spa.example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization,X-Umbod-Web-Request",
    })
    assert response.status_code == 200
    assert "access-control-allow-credentials" not in response.headers
