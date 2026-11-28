import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


def jwt_headers(subject: str, membership: str) -> dict[str, str]:
    token = json.dumps(
        {
            "signature": "trusted",
            "claims": {"sub": subject, "groups": [membership]},
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "availability.json"
    path.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))


@pytest.fixture
def jwt_settings(availability: None) -> APISettings:
    return APISettings(
        rest={"metrics_enabled": False},
        admin_authentication={
            "mode": "jwt",
            "environment": "development",
            "jwt_header_name": "Authorization",
        },
        endpoints={"site_base_url": "https://site.example.com"},
    )


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return jwt_headers("administrator", "umbod-admins")


@pytest.fixture
def member_headers() -> dict[str, str]:
    return jwt_headers("member", "umbod-users")


@pytest.fixture
def client(jwt_settings: APISettings) -> Iterator[TestClient]:
    with TestClient(create_app(jwt_settings, [])) as transport:
        yield transport
