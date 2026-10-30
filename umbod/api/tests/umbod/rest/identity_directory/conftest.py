import json
import urllib.request
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings

ISSUER = "https://identity.example.com/"


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(
    signing_key: rsa.RSAPrivateKey, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    public_key = json.loads(
        jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key())
    )
    public_key["kid"] = "trusted"
    jwks = json.dumps({"keys": [public_key]}).encode()

    def open_jwks(
        request: urllib.request.Request, *, timeout: float, context: object
    ) -> BytesIO:
        return BytesIO(jwks)

    monkeypatch.setattr(urllib.request, "urlopen", open_jwks)
    config = APISettings(
        runtime={"profile": "production", "auth": "auth0"},
        rest={"metrics_enabled": False},
        connector_store={
            "type": "sqlite",
            "sqlite_path": str(tmp_path / "directory.sqlite"),
        },
        admin_authentication={
            "mode": "jwt",
            "environment": "production",
            "jwks_url": ISSUER + "jwks",
            "membership_claim": "admins",
            "required_membership": "admin",
        },
        mcp={"permission_group_claim": "permissions"},
        oidc={"issuer_url": ISSUER, "audience": "umbod-api", "client_id": "web-client"},
        user_profile={"mode": "id_token"},
    )
    with TestClient(create_app(config, [])) as transport:
        yield transport


@pytest.fixture
def auth_headers(signing_key: rsa.RSAPrivateKey) -> dict[str, str]:
    claims = {
        "iss": ISSUER,
        "aud": "umbod-api",
        "sub": "user",
        "admins": ["admin"],
        "exp": int(time()) + 600,
    }
    return {
        "Authorization": "Bearer "
        + jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "trusted"})
    }
