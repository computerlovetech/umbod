import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.rest.main import create_app


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_public_artifacts_are_deterministic_and_use_only_configured_endpoint(
    client: TestClient, harness: str,
) -> None:
    prefix = f"/api/install/v1/{harness}"
    archive = client.get(prefix + "/package.zip")
    spoofed = client.get(
        prefix + "/package.zip?endpoint=https://attacker.test/mcp",
        headers={"Host": "attacker.test", "X-Forwarded-Host": "attacker.test"},
    )
    assert archive.status_code == spoofed.status_code == 200
    assert archive.content == spoofed.content
    assert archive.headers["content-type"] == "application/zip"
    assert archive.headers["content-disposition"] == f'attachment; filename="umbod-{harness}-package.zip"'
    checksum = client.get(prefix + "/package.sha256")
    assert checksum.text == hashlib.sha256(archive.content).hexdigest() + "\n"
    assert re.fullmatch(r"[0-9a-f]{64}\n", checksum.text)
    marketplace = client.get(prefix + "/marketplace.txt")
    assert re.fullmatch(r"umbod-[0-9a-f]{12}\n", marketplace.text)
    endpoint = client.get(prefix + "/endpoint.txt?endpoint=https://evil.test")
    assert endpoint.text == "https://configured.test/team/mcp\n"
    for response in (archive, checksum, marketplace, endpoint):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "set-cookie" not in response.headers
    for response in (checksum, marketplace, endpoint):
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
    with ZipFile(BytesIO(archive.content)) as package:
        mcp = json.loads(package.read("plugins/umbod/.mcp.json"))
        assert mcp == {"mcpServers": {"umbod": {"type": "http", "url": endpoint.text.strip()}}}
        assert all(entry.date_time == (1980, 1, 1, 0, 0, 0) for entry in package.infolist())
        assert all(entry.external_attr >> 16 == 0o100644 for entry in package.infolist())


@pytest.mark.parametrize(("harness", "catalog_path", "manifest_path"), [
    ("codex", ".agents/plugins/marketplace.json", ".codex-plugin"),
    ("claude-code", ".claude-plugin/marketplace.json", ".claude-plugin"),
])
def test_package_contains_actual_harness_schema_and_canonical_resources(
    client: TestClient, harness: str, catalog_path: str, manifest_path: str,
) -> None:
    root = Path(__file__).resolve().parents[6]
    response = client.get(f"/api/install/v1/{harness}/package.zip")
    with ZipFile(BytesIO(response.content)) as package:
        catalog = json.loads(package.read(catalog_path))
        manifest = json.loads(package.read(f"plugins/umbod/{manifest_path}/plugin.json"))
        assert catalog["name"] == client.get(f"/api/install/v1/{harness}/marketplace.txt").text.strip()
        assert manifest["name"] == "umbod"
        assert manifest["skills"] == "./skills/"
        assert manifest["mcpServers"] == "./.mcp.json"
        if harness == "codex":
            assert catalog["plugins"][0]["source"] == {"source": "local", "path": "./plugins/umbod"}
            assert catalog["plugins"][0]["policy"] == {"installation": "AVAILABLE", "authentication": "ON_USE"}
        else:
            assert catalog["owner"]["name"] == "Computerlove"
            assert catalog["plugins"][0]["source"] == "./plugins/umbod"
        assert package.read("plugins/umbod/skills/umbod-connected-apps/SKILL.md") == (
            root / "skills/integrations/umbod-connected-apps/SKILL.md"
        ).read_bytes()
        assert package.read("plugins/umbod/LICENSE") == (root / "LICENSE").read_bytes()


@pytest.mark.parametrize("artifact", ["package.zip", "package.sha256", "marketplace.txt", "endpoint.txt"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_invalid_harness_does_not_bypass_authentication(
    client: TestClient, artifact: str, method: str,
) -> None:
    assert client.request(method, f"/api/install/v1/unknown/{artifact}").status_code == 401


@pytest.mark.parametrize("endpoint", [
    "http://public.test", "https://user:private@configured.test", "https://configured.test?token=private", "",
])
def test_invalid_configured_endpoint_is_rejected_without_leaking_configuration(
    settings: AppConfig, endpoint: str,
) -> None:
    configured = settings.model_copy(update={
        "endpoints": settings.endpoints.model_copy(update={"mcp_base_url": endpoint}),
    })
    with TestClient(create_app(configured, [])) as client:
        response = client.get("/api/install/v1/codex/package.zip")
    assert response.status_code == 503
    assert response.json() == {"detail": "Installation endpoint is not configured"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [
    "/api/install/v1/codex/package.zip/evil", "/api/install/v1/codex/other",
    "/api/install/v2/codex/package.zip", "/api/install-other/v1/codex/package.zip",
    "/api/install/docs", "/api/me/profile", "/api/admin/users",
])
def test_public_get_allowance_does_not_expose_other_paths(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_public_allowance_rejects_mutating_methods(client: TestClient, method: str) -> None:
    assert client.request(method, "/api/install/v1/codex/package.zip").status_code == 401
