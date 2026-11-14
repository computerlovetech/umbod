from collections.abc import Iterator
from pathlib import Path
from typing import NoReturn

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from umbod.config import AppConfig
from umbod.rest.filesystem_administration.deps import get_policy_database
from umbod.rest.main import create_app

PATH = "/api/admin/filesystem/root-access"


@pytest.fixture
def admin_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
        oidc={"issuer_url": " Exact Issuer "},
        mcp={"permission_group_claim": "filesystem_groups"},
    )


@pytest.fixture
def admin_client(admin_settings: AppConfig) -> Iterator[TestClient]:
    with TestClient(create_app(admin_settings, []), raise_server_exceptions=False) as client:
        yield client


def admin_app(client: TestClient) -> FastAPI:
    return next(route.app for route in client.app.routes if isinstance(route, Mount) and route.path == "/api/admin")


def forbid_database() -> NoReturn:
    pytest.fail("Removed root administration must not resolve storage")


@pytest.mark.parametrize("method", ["GET", "PUT", "POST", "DELETE", "OPTIONS"])
def test_root_administration_is_absent_without_storage_access(admin_client: TestClient, method: str) -> None:
    admin_app(admin_client).dependency_overrides[get_policy_database] = forbid_database
    assert admin_client.request(method, PATH, json={"groups": []}).status_code == 404


def test_root_policy_is_absent_from_admin_openapi(admin_client: TestClient) -> None:
    schema = admin_client.get("/api/admin/openapi.json").json()
    assert "/filesystem/root-access" not in schema["paths"]
    assert "/filesystem/namespaces" in schema["paths"]
    assert {"RootGroupPolicyView", "SaveRootGroupPolicy"}.isdisjoint(schema["components"]["schemas"])
