import json
from collections.abc import Iterator
from pathlib import Path
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWK, PyJWKClient

from umbod.config import AppConfig
from umbod.rest.main import create_app

ISSUER = "https://identity.example.test/"


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(
    signing_key: rsa.RSAPrivateKey, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    availability = tmp_path / "availability.json"
    availability.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability)
    )
    key = PyJWK(
        json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    )

    def trusted_key(_client: PyJWKClient, token: str) -> PyJWK:
        return key

    def trusted_keys(_client: PyJWKClient, refresh: bool) -> list[PyJWK]:
        return [key]

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", trusted_key)
    monkeypatch.setattr(PyJWKClient, "get_signing_keys", trusted_keys)
    config = AppConfig(
        rest={"metrics_port": 19688},
        admin_authentication={
            "mode": "jwt",
            "environment": "production",
            "jwks_url": ISSUER + "jwks",
            "jwt_header_name": "X-Access",
        },
        oidc={"issuer_url": ISSUER, "audience": "api", "client_id": "web"},
        user_profile={
            "mode": "id_token",
            "name_claim": "https://profile.test/name",
            "email_claim": "mail",
            "picture_claim": "avatar",
        },
    )
    with TestClient(create_app(config, [])) as transport:
        yield transport


def token(key: rsa.RSAPrivateKey, audience: str, changes: dict[str, object]) -> str:
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": audience,
            "sub": "admin",
            "exp": int(time()) + 600,
            **changes,
        },
        key,
        algorithm="RS256",
    )


def access(key: rsa.RSAPrivateKey) -> str:
    return token(
        key, "api", {"groups": ["umbod-admins"], "https://profile.test/name": "Access"}
    )


def test_valid_id_profile_enriches_access_identity(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    response = client.get(
        "/api/admin/users",
        headers={
            "X-Access": access(signing_key),
            "X-Auth-Request-ID-Token": token(
                signing_key,
                "web",
                {
                    "https://profile.test/name": "Display",
                    "avatar": "https://avatar.test/image",
                    "mail": "mail@test",
                },
            ),
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": "admin",
        "email": "mail@test",
        "name": "Display",
        "picture": "https://avatar.test/image",
    }


@pytest.mark.parametrize(
    "profile", [{}, {"https://profile.test/name": 12, "mail": [], "avatar": False}]
)
def test_valid_id_missing_fields_are_neutral_not_access_fields(
    client: TestClient, signing_key: rsa.RSAPrivateKey, profile: dict[str, object]
) -> None:
    response = client.get(
        "/api/admin/users",
        headers={
            "Authorization": "Bearer " + access(signing_key),
            "X-Auth-Request-ID-Token": token(signing_key, "web", profile),
        },
    )
    assert response.json() == {
        "id": "admin",
        "email": None,
        "name": "unknown",
        "picture": None,
    }


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"exp": int(time()) - 60}, "expired"),
        ({"aud": "api"}, "audience"),
        ({"iss": "https://wrong.test/"}, "issuer"),
        ({"azp": "wrong"}, "authorized_party"),
        ({"aud": ["web", "other"]}, "authorized_party"),
        ({"sub": "other"}, "subject_binding"),
        ({"sub": None}, "invalid_token"),
    ],
)
def test_rejected_profile_falls_back_without_sensitive_logs(
    client: TestClient,
    signing_key: rsa.RSAPrivateKey,
    caplog: pytest.LogCaptureFixture,
    changes: dict[str, object],
    reason: str,
) -> None:
    profile_token = token(
        signing_key,
        "web",
        {
            "mail": "private@test",
            "https://profile.test/name": "SecretProfile",
            **changes,
        },
    )
    response = client.get(
        "/api/admin/users",
        headers={
            "Authorization": "Bearer " + access(signing_key),
            "X-Auth-Request-ID-Token": profile_token,
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Access"
    records = [
        record for record in caplog.records if record.name.endswith("users.id_token")
    ]
    assert [record.reason_category for record in records] == [reason]
    assert profile_token not in caplog.text
    assert "private@test" not in caplog.text
    assert "SecretProfile" not in caplog.text


def test_wrong_signature_profile_is_ignored(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = client.get(
        "/api/admin/users",
        headers={
            "X-Access": access(signing_key),
            "X-Auth-Request-ID-Token": token(
                attacker, "web", {"https://profile.test/name": "Attacker"}
            ),
        },
    )
    assert response.json()["name"] == "Access"


def test_missing_profile_header_does_not_retry_authorization(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    response = client.get(
        "/api/admin/users",
        headers={
            "X-Access": access(signing_key),
            "Authorization": "Bearer "
            + token(signing_key, "web", {"https://profile.test/name": "Ignored"}),
        },
    )
    assert response.json()["name"] == "Access"


@pytest.mark.parametrize(
    "access_header,status",
    [("missing", 401), ("invalid", 401), ("nonadmin", 403), ("id", 401)],
)
def test_profile_never_authorizes(
    client: TestClient, signing_key: rsa.RSAPrivateKey, access_header: str, status: int
) -> None:
    id_token = token(signing_key, "web", {"groups": ["umbod-admins"]})
    headers = {"X-Auth-Request-ID-Token": id_token}
    if access_header == "invalid":
        headers.update(
            {"X-Access": "invalid", "Authorization": "Bearer " + access(signing_key)}
        )
    if access_header == "nonadmin":
        headers["X-Access"] = token(signing_key, "api", {"groups": ["member"]})
    if access_header == "id":
        headers["Authorization"] = "Bearer " + id_token
    assert client.get("/api/admin/users", headers=headers).status_code == status


@pytest.mark.parametrize("profile_token", ["", "not-a-jwt", "Bearer invalid"])
def test_present_malformed_profile_is_ignored(
    client: TestClient, signing_key: rsa.RSAPrivateKey, profile_token: str
) -> None:
    response = client.get(
        "/api/admin/users",
        headers={
            "X-Access": access(signing_key),
            "X-Auth-Request-ID-Token": profile_token,
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Access"


@pytest.mark.parametrize("missing", ["iss", "aud", "exp", "sub"])
def test_profile_required_claims_cannot_be_omitted(
    client: TestClient, signing_key: rsa.RSAPrivateKey, missing: str
) -> None:
    claims = {
        "iss": ISSUER,
        "aud": "web",
        "exp": int(time()) + 600,
        "sub": "admin",
        "https://profile.test/name": "Untrusted",
    }
    claims.pop(missing)
    response = client.get(
        "/api/admin/users",
        headers={
            "X-Access": access(signing_key),
            "X-Auth-Request-ID-Token": jwt.encode(
                claims, signing_key, algorithm="RS256"
            ),
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Access"


def test_profile_dependency_does_not_change_user_openapi(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    schema = client.get(
        "/api/admin/openapi.json", headers={"X-Access": access(signing_key)}
    ).json()
    operation = schema["paths"]["/users"]["get"]
    assert not operation.get("parameters")
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CurrentUserResponse"
    }
    assert set(
        schema["components"]["schemas"]["CurrentUserResponse"]["properties"]
    ) == {"id", "email", "name", "picture"}


def test_multiple_audiences_with_matching_authorized_party_are_valid(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    response = client.get(
        "/api/admin/users",
        headers={
            "X-Access": access(signing_key),
            "X-Auth-Request-ID-Token": token(
                signing_key,
                "web",
                {
                    "aud": ["web", "other"],
                    "azp": "web",
                    "https://profile.test/name": "Display",
                },
            ),
        },
    )
    assert response.json()["name"] == "Display"
