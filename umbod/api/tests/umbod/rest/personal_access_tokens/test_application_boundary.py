import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr

from umbod.config import AppConfig
from umbod.rest.authentication.verifiers import ProductionJwksJwtVerifier
from umbod.rest.main import create_app

ISSUER = "https://identity.example.test/"
SITE = "https://umbod.example.test"
URL = "/api/me/personal-access-tokens"


@dataclass(frozen=True)
class AuthenticatedApi:
    client: TestClient
    login: SecretStr


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def api(
    signing_key: rsa.RSAPrivateKey,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[AuthenticatedApi]:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    key["kid"] = "personal-access-token-boundary-key"
    verifier = ProductionJwksJwtVerifier(ISSUER + "jwks", ISSUER, "api")
    cache = verifier.jwks_client.jwk_set_cache
    assert cache is not None
    cache.put({"keys": [key]})
    settings = AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        endpoints={"site_base_url": SITE},
        admin_authentication={
            "mode": "jwt",
            "environment": "production",
            "jwks_url": ISSUER + "jwks",
        },
        oidc={"issuer_url": ISSUER, "audience": "api"},
    )
    login = SecretStr(
        jwt.encode(
            {
                "iss": ISSUER,
                "aud": "api",
                "sub": "alice",
                "exp": int(time()) + 600,
                "groups": ["members"],
            },
            signing_key,
            algorithm="RS256",
            headers={"kid": "personal-access-token-boundary-key"},
        )
    )
    with TestClient(
        create_app(
            settings=settings,
            connector_registrations=(),
            admin_verifier=verifier,
            user_verifier=verifier,
        )
    ) as client:
        yield AuthenticatedApi(client=client, login=login)


def body() -> dict[str, object]:
    return {
        "name": "Codex on Mac",
        "permissions": {"telemetry": "write"},
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }


def bearer(api: AuthenticatedApi) -> dict[str, str]:
    return {"Authorization": "Bearer " + api.login.get_secret_value()}


def test_old_telemetry_management_route_is_absent(api: AuthenticatedApi) -> None:
    response = api.client.get("/api/me/telemetry/tokens", headers=bearer(api))
    assert response.status_code == 404


def test_mounted_management_requires_login(api: AuthenticatedApi) -> None:
    assert api.client.get(URL).status_code == 401
    assert api.client.post(URL, json=body()).status_code == 401
    created = api.client.post(URL, json=body(), headers=bearer(api))
    assert created.status_code == 201
    assert created.json()["metadata"]["owner"] == {"issuer": ISSUER, "subject": "alice"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://attacker.example.test", "X-Umbod-Web-Request": "1"},
        {"Origin": SITE},
    ],
)
def test_cookie_creation_is_csrf_protected(
    api: AuthenticatedApi,
    headers: dict[str, str],
) -> None:
    response = api.client.post(
        URL,
        json=body(),
        headers={**bearer(api), "Cookie": "gateway=session", **headers},
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert api.client.get(URL, headers=bearer(api)).json() == []


def test_cookie_creation_accepts_trusted_origin_and_request_marker(
    api: AuthenticatedApi,
) -> None:
    response = api.client.post(
        URL,
        json=body(),
        headers={
            **bearer(api),
            "Cookie": "gateway=session",
            "Origin": SITE,
            "X-Umbod-Web-Request": "1",
        },
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"


def test_cookie_revocation_is_csrf_protected(api: AuthenticatedApi) -> None:
    created = api.client.post(URL, json=body(), headers=bearer(api))
    assert created.status_code == 201
    token_id = created.json()["metadata"]["token_id"]
    rejected = api.client.delete(
        URL + "/" + token_id,
        headers={**bearer(api), "Cookie": "gateway=session"},
    )
    assert rejected.status_code == 403
    assert api.client.get(URL, headers=bearer(api)).json()[0]["status"] == "active"


def test_issued_ingestion_token_cannot_authenticate_user_or_admin_requests(
    api: AuthenticatedApi,
) -> None:
    created = api.client.post(URL, json=body(), headers=bearer(api))
    assert created.status_code == 201
    token = SecretStr(created.json()["token"])
    headers = {"Authorization": "Bearer " + token.get_secret_value()}
    for path in (URL, "/api/me/profile", "/api/admin/overview"):
        rejected = api.client.get(path, headers=headers)
        assert rejected.status_code == 401
