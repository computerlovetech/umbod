import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from umbod.config import AppConfig
from umbod.core.harness_plugins.ports import InstallerSource, InstallerSourceReader, ScriptKind
from umbod.rest.install.deps import get_installer_sources
from umbod.rest.main import create_app


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
@pytest.mark.parametrize("kind", ["sh", "ps1"])
def test_public_installer_contains_entire_source_bound_only_to_instance_configuration(
    client: TestClient, settings: AppConfig, harness: str, kind: str,
) -> None:
    path = f"/api/install/v1/{harness}/install.{kind}"
    response = client.get(path)
    spoofed = client.get(
        path + "?base_url=https://attacker.test&harness=unknown&endpoint=https://attacker.test/mcp",
        headers={"Host": "attacker.test", "X-Forwarded-Host": "attacker.test", "X-Forwarded-Proto": "http", "Forwarded": "host=attacker.test;proto=http"},
    )
    assert response.status_code == spoofed.status_code == 200
    assert response.content == spoofed.content
    source = (Path(__file__).resolve().parents[4] / f"src/umbod/rest/install/assets/install.{kind}").read_text()
    package_url = settings.endpoints.api_base_url + "/api/install/v1"
    if kind == "sh":
        assert response.text == (
            "#!/usr/bin/env bash\nset -- --base-url " + package_url + " --harness " + harness
            + " --expected-endpoint https://configured.test/team/mcp\n" + source.split("\n", 1)[1]
        )
    else:
        values = (package_url, harness, "https://configured.test/team/mcp")
        expressions = [
            "([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
            + base64.b64encode(value.encode("utf-8")).decode("ascii") + "')))"
            for value in values
        ]
        assert response.text == (
            "& {\n" + source + "\n} -BaseUrl " + expressions[0] + " -Harness " + expressions[1]
            + " -ExpectedEndpoint " + expressions[2] + "\n"
        )
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"] == f'inline; filename="umbod-{harness}-install.{kind}"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in response.headers
    for placeholder in ("__BASE_URL__", "__MCP_URL__", "{{", "https://attacker.test"):
        assert placeholder not in response.text
    head = client.head(path)
    assert head.status_code == 200
    assert head.content == b""
    for header in ("content-type", "content-length", "content-disposition", "cache-control", "x-content-type-options"):
        assert head.headers[header] == response.headers[header]


@pytest.mark.parametrize("path", [
    "/api/install/v1/unknown/install.sh", "/api/install/v1/codex/install.sh/extra",
    "/api/install/v1/codex/install.exe", "/api/install/v2/codex/install.sh",
    "/api/install/v1/claude-code/install.ps1/extra", "/api/install/v1/codex/INSTALL.SH",
])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_nonfinite_installer_paths_remain_protected(client: TestClient, path: str, method: str) -> None:
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@pytest.mark.parametrize("filename", ["install.sh", "install.ps1"])
def test_installer_public_access_is_limited_to_get_and_head(client: TestClient, method: str, filename: str) -> None:
    assert client.request(method, f"/api/install/v1/codex/{filename}").status_code == 401


@pytest.mark.parametrize(("field", "value"), [
    ("api_base_url", "https://user:secret@api.test"), ("api_base_url", "https://api.test/path"),
    ("api_base_url", "https://api.test?private=secret"), ("api_base_url", "https://api.test\n"),
    ("mcp_base_url", "https://user:secret@mcp.test"), ("mcp_base_url", "https://mcp.test?private=secret"),
])
def test_invalid_installer_configuration_returns_sanitized_nonexecutable_failure(
    settings: AppConfig, field: str, value: str,
) -> None:
    configured = settings.model_copy(update={"endpoints": settings.endpoints.model_copy(update={field: value})})
    with TestClient(create_app(configured, [])) as client:
        response = client.get("/api/install/v1/codex/install.sh")
    assert response.status_code == 503
    assert response.json() == {"detail": "Installation script is unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


class UnavailableInstallerSourceReader:
    def read(self, kind: ScriptKind) -> InstallerSource:
        raise OSError("private filesystem location and secret configuration")


def test_missing_installer_resource_returns_sanitized_failure(settings: AppConfig) -> None:
    app = create_app(settings, [])

    def unavailable_sources() -> InstallerSourceReader:
        return UnavailableInstallerSourceReader()

    install_app = next(route.app for route in app.routes if isinstance(route, Mount) and route.path == "/api/install")
    assert isinstance(install_app, FastAPI)
    install_app.dependency_overrides[get_installer_sources] = unavailable_sources
    with TestClient(app) as client:
        response = client.get("/api/install/v1/codex/install.ps1")
    assert response.status_code == 503
    assert response.json() == {"detail": "Installation script is unavailable"}
    assert response.headers["cache-control"] == "no-store"
