import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import InvalidKeyError, PyJWKError, PyJWTError

from umbod.config import AppConfig
from umbod.rest.main import create_app
from umbod.rest.users.jwks import CachedSigningKeyResolver
from umbod.rest.users.signing_keys import SigningKeyResolver

ISSUER = "https://identity.example.test/"


class JwksFetchProbe:
    def __init__(self, key: PyJWK) -> None:
        self.keys = [key]
        self.fetch_count = 0
        self.started = Event()
        self.release = Event()
        self.release.set()

    def fetch_keys(self, client: PyJWKClient, refresh: bool) -> list[PyJWK]:
        self.fetch_count += 1
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("Test signing-key boundary was not released")
        return self.keys


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def fetch_probe(
    signing_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> JwksFetchProbe:
    key = PyJWK(
        {
            **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key())),
            "kid": "initial",
        }
    )
    probe = JwksFetchProbe(key)

    def access_key(client: PyJWKClient, token: str) -> PyJWK:
        return key

    def fetch_keys(client: PyJWKClient, refresh: bool) -> list[PyJWK]:
        return probe.fetch_keys(client, refresh)

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", access_key)
    monkeypatch.setattr(PyJWKClient, "get_signing_keys", fetch_keys)
    return probe


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    availability = tmp_path / "availability.json"
    availability.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability)
    )
    config = AppConfig(
        rest={"metrics_port": 19788},
        admin_authentication={
            "mode": "jwt",
            "environment": "production",
            "jwks_url": ISSUER + "jwks",
            "jwt_header_name": "X-Custom-Access",
            "debug_enabled": True,
        },
        oidc={"issuer_url": ISSUER, "audience": "api", "client_id": "web"},
        user_profile={"mode": "id_token", "jwt_header_name": "X-Custom-Profile"},
    )
    return create_app(config, [])


@pytest.fixture
def client(app: FastAPI, fetch_probe: JwksFetchProbe) -> Iterator[TestClient]:
    with TestClient(app) as transport:
        yield transport


def token(
    key: rsa.RSAPrivateKey, audience: str, changes: dict[str, object], kid: str
) -> str:
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": audience,
            "sub": "private-subject",
            "exp": int(time()) + 600,
            "name": "Private Name",
            "email": "private@email.test",
            **changes,
        },
        key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def request_headers(key: rsa.RSAPrivateKey) -> dict[str, str]:
    return {
        "X-Custom-Access": token(key, "api", {"groups": ["umbod-admins"]}, "initial"),
        "X-Custom-Profile": token(key, "web", {"name": "Profile Name"}, "initial"),
    }


def test_repeated_requests_share_root_lifespan_jwks_cache(
    client: TestClient, fetch_probe: JwksFetchProbe, signing_key: rsa.RSAPrivateKey
) -> None:
    headers = request_headers(signing_key)
    for _ in range(3):
        assert (
            client.get("/api/admin/users", headers=headers).json()["name"]
            == "Profile Name"
        )
    assert fetch_probe.fetch_count == 1


def test_new_key_identifier_refreshes_shared_cache(
    client: TestClient, fetch_probe: JwksFetchProbe, signing_key: rsa.RSAPrivateKey
) -> None:
    headers = request_headers(signing_key)
    assert client.get("/api/admin/users", headers=headers).status_code == 200
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fetch_probe.keys = [
        PyJWK(
            {
                **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rotated.public_key())),
                "kid": "rotated",
            }
        )
    ]
    headers["X-Custom-Profile"] = token(rotated, "web", {"name": "Rotated"}, "rotated")
    assert client.get("/api/admin/users", headers=headers).json()["name"] == "Rotated"
    assert client.get("/api/admin/users", headers=headers).json()["name"] == "Rotated"
    assert fetch_probe.fetch_count == 2


def test_delayed_profile_fetch_does_not_stall_unrelated_request(
    client: TestClient, fetch_probe: JwksFetchProbe, signing_key: rsa.RSAPrivateKey
) -> None:
    fetch_probe.release.clear()
    with ThreadPoolExecutor(max_workers=2) as executor:
        profile_request = executor.submit(
            client.get, "/api/admin/users", headers=request_headers(signing_key)
        )
        try:
            assert fetch_probe.started.wait(timeout=2)
            health_request = executor.submit(client.get, "/api/system/health")
            assert health_request.result(timeout=1).status_code == 200
            assert not profile_request.done()
        finally:
            fetch_probe.release.set()
        assert profile_request.result(timeout=2).status_code == 200


def test_debug_and_rejected_profile_logs_never_expose_credentials_or_claims(
    client: TestClient, signing_key: rsa.RSAPrivateKey, caplog: pytest.LogCaptureFixture
) -> None:
    headers = request_headers(signing_key)
    headers.update(
        {
            "X-Custom-Profile": token(
                signing_key,
                "web",
                {"azp": "wrong-client", "name": "Rejected Profile"},
                "initial",
            ),
            "Authorization": "Bearer authorization-secret",
            "Cookie": "session=cookie-secret",
            "X-Auth-Request-Email": "forwarded-private@email.test",
            "X-Arbitrary": "unknown-header-secret",
        }
    )
    assert client.get("/api/admin/users", headers=headers).status_code == 200
    records = [
        record for record in caplog.records if record.name.startswith("umbod.rest")
    ]
    serialized = repr([record.__dict__ for record in records])
    for secret in (
        *headers.values(),
        "Private Name",
        "Profile Name",
        "Rejected Profile",
        "private-subject",
        "private@email.test",
        "wrong-client",
    ):
        assert secret not in serialized
    debug = next(
        record
        for record in records
        if record.name.endswith("authentication.debug_middleware")
    )
    assert debug.configured_access_header_present is True
    assert debug.configured_profile_header_present is True
    assert debug.authorization_header_present is True
    assert debug.cookie_header_present is True
    rejection = next(
        record for record in records if record.name.endswith("users.id_token")
    )
    assert rejection.reason_category == "authorized_party"


@pytest.mark.parametrize(
    "error",
    [
        InvalidKeyError("provider-key-secret"),
        PyJWKError("provider-key-secret"),
        ValueError("provider-key-secret"),
        json.JSONDecodeError("provider-key-secret", "provider-secret-document", 0),
    ],
)
def test_malformed_provider_keys_fall_back_without_secret_logs(
    client: TestClient,
    signing_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: PyJWTError | ValueError,
) -> None:
    def malformed_keys(client: PyJWKClient, refresh: bool) -> list[PyJWK]:
        raise error

    monkeypatch.setattr(PyJWKClient, "get_signing_keys", malformed_keys)
    response = client.get("/api/admin/users", headers=request_headers(signing_key))
    assert response.status_code == 200
    assert response.json()["name"] == "Private Name"
    rejection = next(
        record for record in caplog.records if record.name.endswith("users.id_token")
    )
    assert rejection.reason_category == "invalid_token"
    assert "provider-key-secret" not in repr(rejection.__dict__)
    assert "provider-secret-document" not in caplog.text


def test_ec_provider_key_is_rejected_as_optional_profile(
    client: TestClient,
    fetch_probe: JwksFetchProbe,
    signing_key: rsa.RSAPrivateKey,
    caplog: pytest.LogCaptureFixture,
) -> None:
    wrong_key = ec.generate_private_key(ec.SECP256R1())
    fetch_probe.keys = [
        PyJWK(
            {
                **json.loads(jwt.algorithms.ECAlgorithm.to_jwk(wrong_key.public_key())),
                "kid": "initial",
            }
        )
    ]
    response = client.get("/api/admin/users", headers=request_headers(signing_key))
    assert response.status_code == 200
    assert response.json()["name"] == "Private Name"
    rejection = next(
        record for record in caplog.records if record.name.endswith("users.id_token")
    )
    assert rejection.reason_category == "invalid_token"
    assert "Private Name" not in caplog.text


def test_root_lifespan_propagates_shared_resolver_to_requests_and_clears_cache(
    app: FastAPI, fetch_probe: JwksFetchProbe, signing_key: rsa.RSAPrivateKey
) -> None:
    resolvers: list[SigningKeyResolver] = []

    def capture_resolver(request: Request) -> dict[str, bool]:
        resolver = request.state.profile_signing_key_resolver
        assert isinstance(resolver, CachedSigningKeyResolver)
        resolvers.append(resolver)
        return {"available": True}

    app.add_api_route("/test/lifespan-resolver", capture_resolver)
    profile_token = request_headers(signing_key)["X-Custom-Profile"]
    with TestClient(app) as transport:
        assert (
            transport.get(
                "/api/admin/users", headers=request_headers(signing_key)
            ).status_code
            == 200
        )
        assert transport.get("/test/lifespan-resolver").json() == {"available": True}
        assert transport.get("/test/lifespan-resolver").status_code == 200
        assert resolvers[0] is resolvers[1]
        assert resolvers[0].resolve(profile_token).key_id == "initial"
        assert fetch_probe.fetch_count == 1
    assert resolvers[0].resolve(profile_token).key_id == "initial"
    assert fetch_probe.fetch_count == 2


def test_id_profile_requires_started_root_lifespan(
    app: FastAPI, fetch_probe: JwksFetchProbe, signing_key: rsa.RSAPrivateKey
) -> None:
    with pytest.raises(
        RuntimeError, match="Root lifespan profile signing-key resolver is not running"
    ):
        TestClient(app).get("/api/admin/users", headers=request_headers(signing_key))
    assert fetch_probe.fetch_count == 0
