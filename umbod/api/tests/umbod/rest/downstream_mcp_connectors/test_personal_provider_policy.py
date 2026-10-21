from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


SECRET = "personal-policy-secret-must-not-be-reflected"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Iterator[TestClient]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = APISettings(
        rest={"metrics_enabled": False},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "policy.sqlite")},
        connector_security={"configuration_secret": getattr(request, "param", "policy-encryption-key")},
        personal_connections={"enabled": True, "identity_namespace": "test:policy"},
    )
    with TestClient(create_app(settings=settings, connector_registrations=[])) as transport:
        yield transport


def confidential_settings() -> dict[str, object]:
    return {
        "requested_scopes": ["write", "read"],
        "client": {
            "kind": "preconfigured_confidential", "issuer_url": "https://issuer.example",
            "client_id": "client", "client_secret": SECRET,
            "token_endpoint_auth_method": "client_secret_basic",
        },
    }


def creation(settings: dict[str, object]) -> dict[str, object]:
    return {
        "metadata": {"display_name": "Policy", "capability_description": "Policy management", "public_path": "/mcp/proxies/policy"},
        "configuration": {"endpoint_url": "https://127.0.0.1/mcp", "oauth_configuration": settings},
    }


def test_configured_policy_creation_projection_rotation_and_cas(client: TestClient) -> None:
    created = client.post("/api/admin/connectors/mcp/personal-oauth", json=creation(confidential_settings()))
    assert created.status_code == 201
    assert SECRET not in created.text
    assert created.json()["credential_configured"] is False
    policy_url = f'/api/admin/connectors/mcp/{created.json()["connector_id"]}/personal-oauth'
    current = client.get(policy_url)
    assert current.status_code == 200
    assert current.json()["requested_scopes"] == ["read", "write"]
    assert current.json()["client"]["client_secret_configured"] is True
    assert "client_secret" not in current.json()["client"]
    assert SECRET not in current.text
    unchanged_public = {"requested_scopes": ["read"], "client": {"kind": "dynamic_public"}}
    replaced = client.put(policy_url, json={"expected_revision": current.json()["revision"], "settings": unchanged_public})
    assert replaced.status_code == 200
    assert replaced.json()["client"] == {"kind": "dynamic_public"}
    assert replaced.json()["revision"] != current.json()["revision"]
    assert client.put(policy_url, json={"expected_revision": current.json()["revision"], "settings": confidential_settings()}).status_code == 409
    same = client.put(policy_url, json={"expected_revision": replaced.json()["revision"], "settings": unchanged_public})
    assert same.json()["revision"] == replaced.json()["revision"]


@pytest.mark.parametrize("scopes", [
    [""], ["read write"], ["read", "read"], ["read\twrite"], ['quote"'], ["back\\slash"], ["é"],
    ["x" * 257], [f"scope{index}" for index in range(65)], [f"scope{index}" + "x" * 230 for index in range(32)],
])
def test_invalid_scope_policies_are_rejected_without_creation(client: TestClient, scopes: list[str]) -> None:
    settings = {"requested_scopes": scopes, "client": {"kind": "dynamic_public"}}
    response = client.post("/api/admin/connectors/mcp/personal-oauth", json=creation(settings))
    assert response.status_code == 422
    assert client.get("/api/admin/connectors/mcp").json()["connectors"] == []


@pytest.mark.parametrize("invalidity", ("extra", "unknown_kind", "bad_id", "bad_issuer", "unsupported_method", "missing_secret", "metadata", "bad_scopes"))
def test_invalid_confidential_requests_never_reflect_secret_inputs(client: TestClient, invalidity: str) -> None:
    settings = confidential_settings()
    request = creation(settings)
    configured_client = settings["client"]
    assert isinstance(configured_client, dict)
    if invalidity == "extra":
        settings["unexpected"] = SECRET
    elif invalidity == "unknown_kind":
        configured_client["kind"] = "unknown"
    elif invalidity == "bad_id":
        configured_client["client_id"] = "\n"
    elif invalidity == "bad_issuer":
        configured_client["issuer_url"] = "http://issuer.example"
    elif invalidity == "unsupported_method":
        configured_client["token_endpoint_auth_method"] = "private_key_jwt"
    elif invalidity == "missing_secret":
        configured_client.pop("client_secret")
        settings["extra_secret"] = SECRET
    elif invalidity == "metadata":
        request["metadata"] = {"display_name": "", "unexpected": SECRET}
    else:
        settings["requested_scopes"] = ["invalid scope"]
    response = client.post("/api/admin/connectors/mcp/personal-oauth", json=request)
    assert response.status_code == 422
    assert SECRET not in response.text
    assert client.get("/api/admin/connectors/mcp").json()["connectors"] == []


@pytest.mark.parametrize("client", [""], indirect=True)
def test_confidential_writes_require_encryption_before_creation(client: TestClient) -> None:
    response = client.post("/api/admin/connectors/mcp/personal-oauth", json=creation(confidential_settings()))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "personal_oauth_encryption_required"
    assert SECRET not in response.text
    assert client.get("/api/admin/connectors/mcp").json()["connectors"] == []


def test_public_clients_reject_secrets_and_personal_write_json_errors_are_sanitized(client: TestClient) -> None:
    settings = confidential_settings()
    configured_client = settings["client"]
    assert isinstance(configured_client, dict)
    configured_client["kind"] = "preconfigured_public"
    response = client.post("/api/admin/connectors/mcp/personal-oauth", json=creation(settings))
    assert response.status_code == 422
    assert SECRET not in response.text
    malformed = client.post("/api/admin/connectors/mcp/personal-oauth", content='{"client_secret":"' + SECRET + '",', headers={"Content-Type": "application/json"})
    assert malformed.status_code == 422
    assert SECRET not in malformed.text
