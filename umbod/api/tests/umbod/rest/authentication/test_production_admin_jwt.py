import json
from collections.abc import Iterator
from pathlib import Path
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWK, PyJWKClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(signing_key: rsa.RSAPrivateKey, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    availability = tmp_path / "availability.json"
    availability.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability))
    public_key = PyJWK(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key())))

    def trusted_key(_client: PyJWKClient, token: str) -> PyJWK:
        return public_key

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", trusted_key)
    settings = APISettings(
        rest={"metrics_port": 19588},
        admin_authentication={"mode": "jwt", "environment": "production", "jwt_header_name": "X-Auth-Request-Access-Token", "jwks_url": "https://identity.example.com/jwks"},
        oidc={"issuer_url": "https://identity.example.com/", "audience": "umbod-api"},
    )
    with TestClient(create_app(settings, [])) as transport:
        yield transport


def _token(signing_key: rsa.RSAPrivateKey, issuer: str, audience: str) -> str:
    return jwt.encode({"iss": issuer, "aud": audience, "sub": "admin-123", "email": "admin@example.com", "groups": ["umbod-admins"], "exp": int(time()) + 600}, signing_key, algorithm="RS256")


@pytest.mark.parametrize("issuer,audience,status", [
    ("https://identity.example.com/", "umbod-api", 200),
    ("https://attacker.example.com/", "umbod-api", 401),
    ("https://identity.example.com/", "web-client-id", 401),
])
@pytest.mark.parametrize("header", ["Authorization", "X-Auth-Request-Access-Token"])
def test_production_requires_configured_issuer_and_audience(
    client: TestClient, signing_key: rsa.RSAPrivateKey, issuer: str, audience: str, status: int, header: str
) -> None:
    response = client.get("/api/admin/users", headers={header: "Bearer " + _token(signing_key, issuer, audience)})
    assert response.status_code == status
    if status == 200:
        assert response.json()["id"] == "admin-123"


@pytest.mark.parametrize("forwarded", ["invalid", ""])
def test_invalid_selected_forwarded_token_does_not_fall_back_to_bearer(
    client: TestClient, signing_key: rsa.RSAPrivateKey, forwarded: str
) -> None:
    response = client.get("/api/admin/users", headers={
        "X-Auth-Request-Access-Token": forwarded,
        "Authorization": "Bearer " + _token(signing_key, "https://identity.example.com/", "umbod-api"),
    })
    assert response.status_code == 401


@pytest.mark.parametrize("profile", [{}, {"email": None}, {"email": 123}])
@pytest.mark.parametrize("header", ["Authorization", "X-Auth-Request-Access-Token"])
def test_verified_production_profile_without_email(
    client: TestClient, signing_key: rsa.RSAPrivateKey, profile: dict[str, object], header: str
) -> None:
    claims = jwt.decode(_token(signing_key, "https://identity.example.com/", "umbod-api"), options={"verify_signature": False})
    claims.pop("email")
    claims.update(profile)
    token = jwt.encode(claims, signing_key, algorithm="RS256")
    response = client.get("/api/admin/users", headers={header: "Bearer " + token})
    assert response.status_code == 200
    assert response.json() == {"id": "admin-123", "email": None, "name": "unknown", "picture": None}


@pytest.mark.parametrize("changes", [
    {"exp": int(time()) - 60},
    {"iss": "https://attacker.example.com/"},
    {"aud": "web-client-id"},
    {"sub": None},
    {"sub": 123},
])
def test_invalid_production_token_without_email_remains_unauthorized(
    client: TestClient, signing_key: rsa.RSAPrivateKey, changes: dict[str, object]
) -> None:
    claims = {"iss": "https://identity.example.com/", "aud": "umbod-api", "sub": "admin-123", "groups": ["umbod-admins"], "exp": int(time()) + 600, **changes}
    response = client.get("/api/admin/users", headers={"Authorization": "Bearer " + jwt.encode(claims, signing_key, algorithm="RS256")})
    assert response.status_code == 401


def test_production_missing_subject_without_email_is_unauthorized(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    claims = {"iss": "https://identity.example.com/", "aud": "umbod-api", "groups": ["umbod-admins"], "exp": int(time()) + 600}
    response = client.get("/api/admin/users", headers={"Authorization": "Bearer " + jwt.encode(claims, signing_key, algorithm="RS256")})
    assert response.status_code == 401


def test_current_user_openapi_requires_nullable_email(client: TestClient, signing_key: rsa.RSAPrivateKey) -> None:
    response = client.get("/api/admin/openapi.json", headers={
        "Authorization": "Bearer " + _token(signing_key, "https://identity.example.com/", "umbod-api")
    })
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["CurrentUserResponse"]
    assert "email" in schema["required"]
    assert schema["properties"]["email"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert "default" not in schema["properties"]["email"]


def test_wrong_signature_without_email_is_unauthorized(client: TestClient) -> None:
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {"iss": "https://identity.example.com/", "aud": "umbod-api", "sub": "admin-123", "groups": ["umbod-admins"], "exp": int(time()) + 600}
    response = client.get("/api/admin/users", headers={"Authorization": "Bearer " + jwt.encode(claims, attacker_key, algorithm="RS256")})
    assert response.status_code == 401


def test_non_admin_without_email_remains_forbidden(client: TestClient, signing_key: rsa.RSAPrivateKey) -> None:
    claims = {"iss": "https://identity.example.com/", "aud": "umbod-api", "sub": "admin-123", "groups": ["members"], "exp": int(time()) + 600}
    response = client.get("/api/admin/users", headers={"Authorization": "Bearer " + jwt.encode(claims, signing_key, algorithm="RS256")})
    assert response.status_code == 403


def test_forwarded_access_token_takes_precedence_over_wrong_audience_id_token(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    response = client.get("/api/admin/users", headers={
        "X-Auth-Request-Access-Token": _token(signing_key, "https://identity.example.com/", "umbod-api"),
        "Authorization": "Bearer " + _token(signing_key, "https://identity.example.com/", "web-client-id"),
    })
    assert response.status_code == 200


@pytest.mark.parametrize("issuer,audience", [("", "umbod-api"), ("https://identity.example.com/", "")])
def test_production_admin_configuration_requires_issuer_and_audience(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, issuer: str, audience: str
) -> None:
    availability = tmp_path / "availability.json"
    availability.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability))
    settings = APISettings(admin_authentication={"mode": "jwt", "environment": "production"}, oidc={"issuer_url": issuer, "audience": audience})
    with pytest.raises(ValueError, match="issuer and audience"):
        create_app(settings, [])
