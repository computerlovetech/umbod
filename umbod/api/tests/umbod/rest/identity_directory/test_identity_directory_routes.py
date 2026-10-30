from pathlib import Path
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings

ISSUER = "https://identity.example.com/"


def headers(key: rsa.RSAPrivateKey, **changes: object) -> dict[str, str]:
    claims = {
        "iss": ISSUER,
        "aud": "umbod-api",
        "sub": "user",
        "admins": ["admin"],
        "permissions": [" Team/a ", "team", "", None, {"secret": "value"}, 12],
        "exp": int(time()) + 600,
        **changes,
    }
    return {
        "Authorization": "Bearer "
        + jwt.encode(claims, key, algorithm="RS256", headers={"kid": "trusted"})
    }


def test_ordinary_user_observation_and_admin_only_scoped_search(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    admin_headers = headers(signing_key)
    root_access = client.get(
        "/api/admin/filesystem/root-access", headers=admin_headers
    ).json()
    permission_groups = client.get(
        "/api/admin/mcp-permissions/groups", headers=admin_headers
    ).json()
    user_headers = headers(signing_key, admins=[])
    assert (
        client.post("/api/me/identity-observations", headers=user_headers).status_code
        == 204
    )
    for route in ("groups", "users"):
        assert (
            client.get(
                "/api/admin/identity-directory/" + route, headers=user_headers
            ).status_code
            == 403
        )
        assert client.get("/api/admin/identity-directory/" + route).status_code == 401
    admin_headers = headers(signing_key)
    result = client.get("/api/admin/identity-directory/groups", headers=admin_headers)
    assert result.status_code == 200
    assert set(result.json()) == {"issuer", "claim", "groups", "has_more"}
    assert result.json()["issuer"] == ISSUER
    assert result.json()["claim"] == "permissions"
    assert [group["value"] for group in result.json()["groups"]] == [" Team/a ", "team"]
    assert client.get("/api/admin/groups", headers=admin_headers).json() == {
        "groups": []
    }
    assert (
        client.get("/api/admin/filesystem/root-access", headers=admin_headers).json()
        == root_access
    )
    assert (
        client.get("/api/admin/mcp-permissions/groups", headers=admin_headers).json()
        == permission_groups
    )
    users = client.get(
        "/api/admin/identity-directory/users", headers=admin_headers
    ).json()["users"]
    assert users[0]["subject"] == "user"
    assert users[0]["name"] == ""


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://wrong/"},
        {"sub": " "},
        {"sub": ""},
        {"exp": 0},
        {"aud": "wrong"},
    ],
)
def test_invalid_identity_is_rejected(
    client: TestClient, signing_key: rsa.RSAPrivateKey, changes: dict[str, object]
) -> None:
    assert (
        client.post(
            "/api/me/identity-observations", headers=headers(signing_key, **changes)
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/admin/identity-directory/users", headers=headers(signing_key)
        ).json()["users"]
        == []
    )


@pytest.mark.parametrize("body", [b"{}", b"null", b" ", b'{"groups":["injected"]}'])
def test_any_payload_is_rejected(
    client: TestClient, signing_key: rsa.RSAPrivateKey, body: bytes
) -> None:
    assert (
        client.post(
            "/api/me/identity-observations", headers=headers(signing_key), content=body
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/admin/identity-directory/users", headers=headers(signing_key)
        ).json()["users"]
        == []
    )


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "issuer=https://override",
        "claim=admins",
        "query=" + "a" * 1001,
    ],
)
def test_search_rejects_invalid_limits_and_source_overrides(
    client: TestClient, signing_key: rsa.RSAPrivateKey, query: str
) -> None:
    assert (
        client.get(
            "/api/admin/identity-directory/groups?" + query,
            headers=headers(signing_key),
        ).status_code
        == 422
    )


def test_bound_profile_enrichment_never_supplies_groups_or_mixed_verification(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    request_headers = headers(
        signing_key, email="access@example.test", email_verified=True
    )
    profile = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "user",
            "aud": "web-client",
            "exp": int(time()) + 600,
            "name": "Real Name",
            "email": "profile@example.test",
            "permissions": ["id-only"],
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "trusted"},
    )
    request_headers["X-Auth-Request-Id-Token"] = profile
    assert (
        client.post(
            "/api/me/identity-observations", headers=request_headers
        ).status_code
        == 204
    )
    user = client.get(
        "/api/admin/identity-directory/users", headers=headers(signing_key)
    ).json()["users"][0]
    assert (user["name"], user["email"], user["email_verification"]) == (
        "Real Name",
        "profile@example.test",
        "unknown",
    )
    groups = client.get(
        "/api/admin/identity-directory/groups", headers=headers(signing_key)
    ).json()["groups"]
    assert "id-only" not in [group["value"] for group in groups]


def test_invalid_profile_falls_back_without_losing_discovery(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    request_headers = headers(
        signing_key,
        name="Access Name",
        email="access@example.test",
        email_verified=False,
    )
    request_headers["X-Auth-Request-Id-Token"] = "invalid"
    assert (
        client.post(
            "/api/me/identity-observations", headers=request_headers
        ).status_code
        == 204
    )
    user = client.get(
        "/api/admin/identity-directory/users", headers=headers(signing_key)
    ).json()["users"][0]
    assert (user["name"], user["email"], user["email_verification"]) == (
        "Access Name",
        "access@example.test",
        "unverified",
    )


def test_local_simulation_is_accepted_but_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    config = APISettings(
        admin_authentication={"mode": "simulation", "simulated_admin": True},
        rest={"metrics_enabled": False},
    )
    with TestClient(create_app(config, [])) as transport:
        assert transport.post("/api/me/identity-observations").status_code == 204
        assert (
            transport.get("/api/admin/identity-directory/users").json()["users"] == []
        )
