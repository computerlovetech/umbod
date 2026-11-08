import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from time import time
from unittest.mock import AsyncMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.persistence_runtime import create_inmemory_runtime

from umbod.config import AppConfig
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.authentication.verifiers import ProductionJwksJwtVerifier
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories

URL = "/api/me/telemetry/setup"
ISSUER = "https://identity.example.test/"


@dataclass(frozen=True)
class SetupApi:
    client: TestClient
    runtime: PersistenceRuntime


@pytest.fixture
def settings() -> AppConfig:
    return AppConfig(
        rest={"metrics_enabled": False},
        endpoints={"collector_base_url": "https://collector.example.test/otlp/"},
        otlp_receiver={"enabled": True, "bearer_token": "private-ingestion-secret"},
    )


@pytest.fixture
def api(
    settings: AppConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SetupApi]:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    with TestClient(create_app_with_dependency_factories(factories)) as client:
        yield SetupApi(client=client, runtime=runtime)


def test_local_setup_uses_only_configured_public_url_without_database_read(
    api: SetupApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    readiness = AsyncMock(side_effect=RuntimeError("database must not be used"))
    monkeypatch.setattr(api.runtime.readiness, "ensure_ready", readiness)
    response = api.client.get(
        URL,
        headers={
            "Forwarded": "proto=https;host=attacker.test",
            "X-Forwarded-Host": "attacker.test",
            "X-Forwarded-Proto": "https",
            "Origin": "https://attacker.test",
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "available",
        "logs_endpoint": "https://collector.example.test/otlp/v1/logs",
    }
    readiness.assert_not_awaited()


@pytest.mark.parametrize(
    "enabled,base_url,reason",
    [
        (False, "", "disabled"),
        (False, "https://collector.example.test", "disabled"),
        (True, "", "not_configured"),
    ],
)
def test_setup_unavailability_is_explicit_without_header_fallback(
    api: SetupApi, settings: AppConfig, enabled: bool, base_url: str, reason: str
) -> None:
    settings.otlp_receiver.enabled = enabled
    settings.endpoints.collector_base_url = base_url
    response = api.client.get(
        URL, headers={"X-Forwarded-Host": "collector.test", "X-Forwarded-Proto": "https"}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "unavailable", "reason": reason}


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("runtime", "profile", "production"),
        ("runtime", "auth", "oidc"),
        ("admin_authentication", "mode", "jwt"),
        ("admin_authentication", "environment", "production"),
        ("admin_authentication", "simulated_user_id", " "),
    ],
)
def test_setup_rejects_simulation_outside_strict_local_gate(
    api: SetupApi, settings: AppConfig, section: str, field: str, value: str
) -> None:
    setattr(getattr(settings, section), field, value)
    response = api.client.get(URL)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_setup_accepts_verified_nonadministrator_and_denies_missing_or_forged_login(
    settings: AppConfig,
    signing_key: rsa.RSAPrivateKey,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings.admin_authentication.mode = "jwt"
    settings.admin_authentication.environment = "production"
    settings.admin_authentication.jwks_url = ISSUER + "jwks"
    settings.oidc.issuer_url = ISSUER
    settings.oidc.audience = "api"
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    key["kid"] = "setup-key"
    verifier = ProductionJwksJwtVerifier(ISSUER + "jwks", ISSUER, "api")
    cache = verifier.jwks_client.jwk_set_cache
    assert cache is not None
    cache.put({"keys": [key]})
    login = SecretStr(jwt.encode(
        {"iss": ISSUER, "aud": "api", "sub": "member", "groups": ["members"], "exp": int(time()) + 600},
        signing_key, algorithm="RS256", headers={"kid": "setup-key"},
    ))
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    with TestClient(create_app_with_dependency_factories(
        factories, admin_verifier=verifier, user_verifier=verifier,
    )) as client:
        headers = {"Authorization": "Bearer " + login.get_secret_value()}
        response = client.get(URL, headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "status": "available",
            "logs_endpoint": "https://collector.example.test/otlp/v1/logs",
        }
        assert client.get("/api/me/profile", headers=headers).json()["capabilities"]["administration"] is False
        for denied_headers in ({}, {"Authorization": "Bearer forged"}):
            denied = client.get(URL, headers=denied_headers)
            assert denied.status_code == 401
            assert denied.headers["cache-control"] == "no-store"
            assert "collector" not in denied.text
