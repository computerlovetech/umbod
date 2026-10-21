import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.core.connectors.downstream_mcp.connection import DownstreamMcpConnectionConfiguration
from umbod.core.connectors.downstream_mcp.probe import ProbeResult
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe, get_downstream_stores
from umbod.rest.main import create_app


class UserVerifier:
    def verify(self, token: str) -> JwtClaims:
        subjects = {
            "alice": {"sub": "alice", "groups": ["team"]},
            "bob": {"sub": "bob", "groups": ["team"]},
            "administrator": {"sub": "administrator", "groups": ["admins"]},
            "unmapped": {"email": "alice@example.test", "groups": ["team"]},
        }
        if token not in subjects:
            raise JwtVerificationError("Invalid token")
        return JwtClaims(claims=subjects[token])


class ForbiddenProbe:
    async def probe(self, configuration: DownstreamMcpConnectionConfiguration) -> ProbeResult:
        raise AssertionError("Personal catalogue operations must not contact downstream")


@dataclass(frozen=True)
class PersonalApi:
    client: TestClient
    settings: AppConfig
    admin_headers: dict[str, str]
    connector_id: str
    personal_app: FastAPI

    def headers(self, subject: str) -> dict[str, str]:
        return {"X-Access": subject}

    @property
    def url(self) -> str:
        return "/api/me/connectors/mcp/" + self.connector_id


def _create_connector(client: TestClient, headers: dict[str, str], slug: str) -> str:
    response = client.post("/api/admin/connectors/mcp/personal-oauth", headers=headers, json={
        "metadata": {
            "display_name": slug.title(), "capability_description": "Personal account capabilities",
            "public_path": "/mcp/proxies/" + slug,
        },
        "configuration": {"endpoint_url": "https://tools.example/mcp"},
    })
    response.raise_for_status()
    return response.json()["connector_id"]


@pytest.fixture
def personal_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[PersonalApi]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "personal.sqlite3")},
        rest={"metrics_enabled": False},
        admin_authentication={
            "mode": "jwt", "environment": "development", "required_membership": "admins",
            "membership_claim": "groups", "jwt_header_name": "X-Access",
        },
        mcp={"permission_group_claim": "groups"},
        personal_connections={"enabled": True, "identity_namespace": "test:personal-api"},
    )
    app = create_app(settings, [], user_verifier=UserVerifier())
    admin_app = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/admin")
    personal_app = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/me")
    admin_app.dependency_overrides[get_downstream_connector_probe] = ForbiddenProbe
    admin_headers = {"X-Access": json.dumps({
        "signature": "trusted", "claims": {"sub": "admin", "groups": ["admins"]},
    })}
    with TestClient(app) as client:
        connector_id = _create_connector(client, admin_headers, "personal")
        client.put(f"/api/admin/connectors/mcp/{connector_id}/publication", headers=admin_headers).raise_for_status()
        client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=admin_headers, json={
            "connectors": [{"connector_id": connector_id, "permission_status": "enabled"}],
        }).raise_for_status()
        yield PersonalApi(client, settings, admin_headers, connector_id, personal_app)


def test_non_admin_catalogue_contains_only_safe_eligible_projection(personal_api: PersonalApi) -> None:
    response = personal_api.client.get("/api/me/connectors/mcp", headers=personal_api.headers("alice"))
    assert response.status_code == 200
    assert response.json() == {"connectors": [{
        "connector_id": personal_api.connector_id,
        "display_name": "Personal",
        "capability_description": "Personal account capabilities",
        "enabled": False, "has_authorization": False,
        "runtime_available": False, "runtime_unavailable_reason": "personal_oauth_not_supported",
    }]}
    non_admin_claims = {"X-Access": json.dumps({
        "signature": "trusted", "claims": {"sub": "alice", "groups": ["team"]},
    })}
    assert personal_api.client.get("/api/admin/connectors/mcp", headers=non_admin_claims).status_code == 403
    assert personal_api.client.get("/api/me/connectors/mcp", headers=personal_api.headers("administrator")).json() == {"connectors": []}


def test_enablement_is_explicit_idempotent_and_isolated_between_users(personal_api: PersonalApi) -> None:
    alice = personal_api.headers("alice")
    bob = personal_api.headers("bob")
    enabled = personal_api.client.put(personal_api.url + "/enablement", headers=alice, json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["has_authorization"] is False
    assert enabled.json()["runtime_available"] is False
    repeated = personal_api.client.put(personal_api.url + "/enablement", headers=alice, json={"enabled": True})
    assert repeated.json() == enabled.json()
    assert personal_api.client.get(personal_api.url, headers=bob).json()["enabled"] is False
    assert personal_api.client.delete(personal_api.url + "/authorization", headers=alice).status_code == 204
    assert personal_api.client.get(personal_api.url, headers=alice).json()["enabled"] is False


@pytest.mark.parametrize("withdrawal", ["publication", "grant"])
def test_withdrawn_eligibility_hides_connection_but_preserves_owner_cleanup(
    personal_api: PersonalApi, withdrawal: str,
) -> None:
    alice = personal_api.headers("alice")
    personal_api.client.put(personal_api.url + "/enablement", headers=alice, json={"enabled": True}).raise_for_status()
    if withdrawal == "publication":
        personal_api.client.delete(
            f"/api/admin/connectors/mcp/{personal_api.connector_id}/publication",
            headers=personal_api.admin_headers,
        ).raise_for_status()
    else:
        personal_api.client.put(
            "/api/admin/mcp-permissions/groups/team/permissions", headers=personal_api.admin_headers,
            json={"connectors": [{"connector_id": personal_api.connector_id, "permission_status": "disabled"}]},
        ).raise_for_status()
    assert personal_api.client.get("/api/me/connectors/mcp", headers=alice).json() == {"connectors": []}
    assert personal_api.client.get(personal_api.url, headers=alice).status_code == 404
    assert personal_api.client.put(personal_api.url + "/enablement", headers=alice, json={"enabled": True}).status_code == 404
    assert personal_api.client.put(personal_api.url + "/enablement", headers=alice, json={"enabled": False}).status_code == 200
    assert personal_api.client.delete(personal_api.url + "/authorization", headers=alice).status_code == 204
    assert personal_api.client.delete(personal_api.url + "/authorization", headers=alice).status_code == 204
    assert personal_api.client.delete(personal_api.url + "/authorization", headers=personal_api.headers("bob")).status_code == 404


@pytest.mark.parametrize("headers,expected", [
    ({}, 401), ({"X-Access": "invalid"}, 401), ({"X-Access": "unmapped"}, 403),
    ({"X-Access": "", "Authorization": "Bearer alice"}, 401),
    ({"X-Access": "invalid", "Authorization": "Bearer alice"}, 401),
])
def test_authentication_rejects_before_inventory_access(
    personal_api: PersonalApi, headers: dict[str, str], expected: int,
) -> None:
    def forbidden_stores() -> None:
        raise AssertionError("Rejected identity must not access personal state")

    personal_api.personal_app.dependency_overrides[get_downstream_stores] = forbidden_stores
    response = personal_api.client.get("/api/me/connectors/mcp", headers=headers)
    assert response.status_code == expected


@pytest.mark.parametrize("body", [
    {"enabled": "true"}, {"enabled": 1}, {"enabled": None},
    {"enabled": True, "owner_id": "bob"},
    {"enabled": True, "authorization": "secret-canary"},
])
def test_enablement_rejects_non_boolean_and_owner_or_credential_fields(
    personal_api: PersonalApi, body: dict[str, Any],
) -> None:
    headers = personal_api.headers("alice")
    response = personal_api.client.put(personal_api.url + "/enablement", headers=headers, json=body)
    assert response.status_code == 422
    assert personal_api.client.get(personal_api.url, headers=headers).json()["enabled"] is False


def test_cookie_mutations_require_trusted_origin_and_marker(personal_api: PersonalApi) -> None:
    headers = {**personal_api.headers("alice"), "Cookie": "session=fixture"}
    url = personal_api.url + "/enablement"
    assert personal_api.client.put(url, headers=headers, json={"enabled": True}).status_code == 403
    trusted = {**headers, "Origin": personal_api.settings.endpoints.site_base_url, "X-Umbod-Web-Request": "1"}
    assert personal_api.client.put(url, headers=trusted, json={"enabled": True}).status_code == 200
    assert personal_api.client.delete(personal_api.url + "/authorization", headers=headers).status_code == 403
    assert personal_api.client.delete(personal_api.url + "/authorization", headers=trusted).status_code == 204


def test_authorization_header_fallback_is_supported(personal_api: PersonalApi) -> None:
    response = personal_api.client.get("/api/me/connectors/mcp", headers={"Authorization": "Bearer alice"})
    assert response.status_code == 200
    assert len(response.json()["connectors"]) == 1


def test_unpublished_and_ungranted_definitions_are_not_visible(personal_api: PersonalApi) -> None:
    unpublished = _create_connector(personal_api.client, personal_api.admin_headers, "unpublished")
    ungranted = _create_connector(personal_api.client, personal_api.admin_headers, "ungranted")
    personal_api.client.put(
        f"/api/admin/connectors/mcp/{ungranted}/publication", headers=personal_api.admin_headers,
    ).raise_for_status()
    headers = personal_api.headers("alice")
    for connector_id in (unpublished, ungranted):
        assert personal_api.client.get("/api/me/connectors/mcp/" + connector_id, headers=headers).status_code == 404
    items = personal_api.client.get("/api/me/connectors/mcp", headers=headers).json()["connectors"]
    assert [item["connector_id"] for item in items] == [personal_api.connector_id]


def test_personal_openapi_is_authenticated_and_documents_only_personal_surface(personal_api: PersonalApi) -> None:
    assert personal_api.client.get("/api/me/openapi.json").status_code == 401
    schema = personal_api.client.get("/api/me/openapi.json", headers=personal_api.headers("alice")).json()
    assert schema["servers"] == [{"url": "/api/me"}]
    assert "/connectors/mcp/{connector_id}/enablement" in schema["paths"]
    assert "/connectors/mcp/personal-oauth" not in schema["paths"]
