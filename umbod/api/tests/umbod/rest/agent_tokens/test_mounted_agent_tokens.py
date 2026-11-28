import json
from collections.abc import Iterator
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from umbod.config import AppConfig
from umbod.rest.main import create_app

BASE = "/api/admin/tokens/agents"
GROUP = "agent-readers"
ADMIN_MEMBERSHIP = "platform-operator"
ADMIN_CLAIM = "organization_roles"
ACCESS_HEADER = "X-Forwarded-Access-Token"


def _jwt_headers(claims: dict[str, object]) -> dict[str, str]:
    token = json.dumps({"signature": "trusted", "claims": {"sub": "alice", **claims}})
    return {ACCESS_HEADER: "Bearer " + token}


def _expiry(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _register_group(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/api/admin/groups", headers=headers, json={"group_id": GROUP})
    assert response.status_code == 204


def _create_agent(client: TestClient, headers: dict[str, str], **overrides: object) -> Response:
    return client.post(BASE, headers=headers, json={
        "display_name": "Read-only worker", "group_id": GROUP, "expires_at": _expiry(30), **overrides,
    })


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        runtime={"profile": "local", "auth": "dev"},
        admin_authentication={
            "mode": "jwt", "environment": "development", "simulated_admin": True,
            "jwt_header_name": ACCESS_HEADER, "membership_claim": ADMIN_CLAIM,
            "required_membership": ADMIN_MEMBERSHIP,
        },
        mcp={"permission_group_claim": "groups"},
    )


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return _jwt_headers({ADMIN_CLAIM: ["other", 42, ADMIN_MEMBERSHIP], "groups": [GROUP]})


@pytest.fixture
def client(settings: AppConfig) -> Iterator[TestClient]:
    with TestClient(create_app(settings, [])) as transport:
        yield transport


def test_administrator_issues_and_rotates_secrets_but_lists_only_metadata(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    _register_group(client, admin_headers)
    created = _create_agent(client, admin_headers)
    assert created.status_code == 201
    issued = created.json()
    assert set(issued) == {"metadata", "token"}
    metadata = issued["metadata"]
    assert set(metadata) == {"agent_id", "display_name", "group_id", "credential_id", "expires_at", "status"}
    assert metadata["group_id"] == GROUP
    assert metadata["status"] == "active"
    assert metadata["display_name"] == "Read-only worker"
    agent_path = f"{BASE}/{metadata['agent_id']}"

    rotated = client.post(agent_path + "/rotate", headers=admin_headers, json={"expires_at": _expiry(60)})
    assert rotated.status_code == 200
    renewed = rotated.json()
    assert set(renewed) == {"metadata", "token"}
    assert renewed["metadata"]["agent_id"] == metadata["agent_id"]
    assert renewed["metadata"]["credential_id"] != metadata["credential_id"]
    assert renewed["metadata"]["expires_at"] != metadata["expires_at"]
    assert renewed["token"] != issued["token"]

    listed = client.get(BASE, headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json() == [renewed["metadata"]]
    assert issued["token"] not in listed.text
    assert renewed["token"] not in listed.text
    assert all(response.headers["cache-control"] == "no-store" for response in (created, rotated, listed))


def test_explicit_null_creation_is_listed_as_active_without_expiry(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    _register_group(client, admin_headers)

    created = _create_agent(client, admin_headers, expires_at=None)

    assert created.status_code == 201
    metadata = created.json()["metadata"]
    assert metadata["expires_at"] is None
    assert metadata["status"] == "active"
    listed = client.get(BASE, headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json() == [metadata]


def test_rotation_to_explicit_null_replaces_a_finite_expiry(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    _register_group(client, admin_headers)
    created = _create_agent(client, admin_headers)
    assert created.status_code == 201
    original = created.json()["metadata"]
    assert isinstance(original["expires_at"], str)

    rotated = client.post(
        f"{BASE}/{original['agent_id']}/rotate", headers=admin_headers, json={"expires_at": None},
    )

    assert rotated.status_code == 200
    replacement = rotated.json()["metadata"]
    assert replacement["expires_at"] is None
    assert replacement["credential_id"] != original["credential_id"]
    listed = client.get(BASE, headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json() == [replacement]


def test_revoke_reports_already_revoked_and_unknown_credentials_as_not_found(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    _register_group(client, admin_headers)
    created = _create_agent(client, admin_headers)
    assert created.status_code == 201
    agent_id = created.json()["metadata"]["agent_id"]
    revoked = client.delete(f"{BASE}/{agent_id}", headers=admin_headers)
    assert revoked.status_code == 204
    assert revoked.content == b""
    assert revoked.headers["cache-control"] == "no-store"
    for requested_id in (agent_id, "0" * 32):
        response = client.delete(f"{BASE}/{requested_id}", headers=admin_headers)
        assert response.status_code == 404
        assert response.json() == {"detail": "Agent not found"}
        assert response.headers["cache-control"] == "no-store"
    assert client.get(BASE, headers=admin_headers).json()[0]["status"] == "revoked"


@pytest.mark.parametrize("method,path", [("GET", BASE), ("POST", BASE), ("POST", BASE + "/invalid/rotate"), ("DELETE", BASE + "/invalid")])
def test_agent_management_requires_the_configured_admin_claim(
    client: TestClient, method: str, path: str,
) -> None:
    headers = _jwt_headers({ADMIN_CLAIM: ADMIN_MEMBERSHIP, "groups": [ADMIN_MEMBERSHIP]})
    response = client.request(method, path, headers=headers)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_agent_management_fails_closed_when_admin_authentication_is_disabled(
    settings: AppConfig, admin_headers: dict[str, str],
) -> None:
    settings = settings.model_copy(update={
        "admin_authentication": settings.admin_authentication.model_copy(update={"mode": "disabled"}),
    })
    with TestClient(create_app(settings, [])) as disabled:
        assert disabled.get("/api/admin/groups").status_code == 200
        for method, path in (("GET", BASE), ("POST", BASE), ("POST", BASE + "/invalid/rotate"), ("DELETE", BASE + "/invalid")):
            response = disabled.request(method, path, headers=admin_headers)
            assert response.status_code == 401
            assert response.headers["cache-control"] == "no-store"


def test_cookie_authenticated_mutations_retain_csrf_protection(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    response = _create_agent(client, {**admin_headers, "Cookie": "gateway=session"})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("wire_expiry", ["past", "naive", "invalid", "never"])
def test_issuance_rejects_invalid_expiry_without_echoing_input(
    client: TestClient, admin_headers: dict[str, str], wire_expiry: str,
) -> None:
    _register_group(client, admin_headers)
    expiry = {
        "past": _expiry(-1),
        "naive": "2100-01-01T00:00:00",
        "invalid": "sensitive-input",
        "never": "never",
    }[wire_expiry]
    response = _create_agent(client, admin_headers, expires_at=expiry)
    assert response.status_code == 422
    assert response.json() == {"detail": "Expiry must be in the future" if wire_expiry == "past" else "Invalid agent token request"}
    assert response.headers["cache-control"] == "no-store"


def test_creation_requires_an_explicit_expiry_field(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    _register_group(client, admin_headers)

    response = client.post(
        BASE, headers=admin_headers, json={"display_name": "Read-only worker", "group_id": GROUP},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid agent token request"}


@pytest.mark.parametrize("body", [{}, {"expires_at": "2100-01-01T00:00:00"}])
def test_rotation_requires_an_explicit_null_or_timezone_aware_expiry(
    client: TestClient, admin_headers: dict[str, str], body: dict[str, object],
) -> None:
    _register_group(client, admin_headers)
    created = _create_agent(client, admin_headers)
    assert created.status_code == 201
    metadata = created.json()["metadata"]

    response = client.post(f"{BASE}/{metadata['agent_id']}/rotate", headers=admin_headers, json=body)

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid agent token request"}
    assert client.get(BASE, headers=admin_headers).json() == [metadata]


def test_rotation_rejects_past_expiry_without_replacing_credential(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    _register_group(client, admin_headers)
    created = _create_agent(client, admin_headers)
    assert created.status_code == 201
    metadata = created.json()["metadata"]
    response = client.post(
        f"{BASE}/{metadata['agent_id']}/rotate", headers=admin_headers, json={"expires_at": _expiry(-1)},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Expiry must be in the future"}
    assert client.get(BASE, headers=admin_headers).json() == [metadata]


def test_rotation_rejects_and_redacts_every_field_other_than_expiry(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    response = client.post(
        f"{BASE}/{'0' * 32}/rotate", headers=admin_headers,
        json={"expires_at": _expiry(60), "private-field": "private-value"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid agent token request"}
    assert response.headers["cache-control"] == "no-store"


def test_invalid_agent_id_is_rejected_without_echoing_the_path(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    response = client.delete(f"{BASE}/sensitive-input", headers=admin_headers)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid agent token request"}
    assert response.headers["cache-control"] == "no-store"


def test_unknown_group_and_agent_have_fixed_not_found_responses(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    create_failure = _create_agent(client, admin_headers, group_id="unknown-private-group")
    rotate_failure = client.post(
        f"{BASE}/{'0' * 32}/rotate", headers=admin_headers, json={"expires_at": _expiry(30)},
    )
    assert create_failure.status_code == rotate_failure.status_code == 404
    assert create_failure.json() == {"detail": "Agent group not found"}
    assert rotate_failure.json() == {"detail": "Agent not found"}
    assert create_failure.headers["cache-control"] == rotate_failure.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("mode", ["jwt", "simulation", "disabled"])
def test_issued_agent_bearer_is_not_a_rest_identity(
    settings: AppConfig, admin_headers: dict[str, str], mode: str,
) -> None:
    rest_settings = settings.model_copy(update={
        "admin_authentication": settings.admin_authentication.model_copy(update={"mode": mode}),
    })
    with ExitStack() as clients:
        rest = clients.enter_context(TestClient(create_app(rest_settings, [])))
        issuer = clients.enter_context(TestClient(create_app(settings, []))) if mode == "disabled" else rest
        issuance_headers = {} if mode == "simulation" else admin_headers
        _register_group(issuer, issuance_headers)
        issued = _create_agent(issuer, issuance_headers)
        assert issued.status_code == 201
        bearer = "Bearer " + issued.json()["token"]
        if mode == "simulation":
            assert rest.get(BASE).status_code == 200
            assert rest.get("/api/me/profile").status_code == 200
        paths = (BASE, "/api/admin/groups", "/api/me/profile")
        for path in paths:
            response = rest.get(path, headers={"Authorization": bearer})
            assert response.status_code == 401
            assert response.json() == {"detail": "Unauthorized"}
            assert response.headers["cache-control"] == "no-store"
        assert rest.get("/api/system/health", headers={"Authorization": bearer}).status_code == 200


def test_agent_detection_respects_configured_header_precedence(
    client: TestClient, admin_headers: dict[str, str],
) -> None:
    _register_group(client, admin_headers)
    issued = _create_agent(client, admin_headers)
    assert issued.status_code == 201
    bearer = "Bearer " + issued.json()["token"]
    valid = admin_headers[ACCESS_HEADER]
    assert client.get(BASE, headers={ACCESS_HEADER: valid, "Authorization": bearer}).status_code == 200
    assert client.get(BASE, headers={ACCESS_HEADER: bearer, "Authorization": valid}).status_code == 401
