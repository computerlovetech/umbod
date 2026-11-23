import base64
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest

from conftest import RuntimeEndpoints


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_running_public_plugin_artifacts_use_configured_endpoint(
    runtime_endpoints: RuntimeEndpoints, harness: str,
) -> None:
    expected_endpoint = "https://mcp.umbod.example.invalid/mcp"
    expected_marketplace = "umbod-" + hashlib.sha256(expected_endpoint.encode("utf-8")).hexdigest()[:12]
    prefix = f"/api/install/v1/{harness}"
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=10, trust_env=False) as client:
        responses = {
            artifact: client.get(f"{prefix}/{artifact}")
            for artifact in ("package.zip", "package.sha256", "endpoint.txt", "marketplace.txt")
        }
        for artifact, response in responses.items():
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["content-disposition"] == f'attachment; filename="umbod-{harness}-{artifact}"'
            assert "set-cookie" not in response.headers
            head = client.head(f"{prefix}/{artifact}")
            assert head.status_code == 200
            assert head.content == b""
            for header in (
                "content-type", "content-length", "content-disposition", "cache-control", "x-content-type-options",
            ):
                assert head.headers[header] == response.headers[header]
        archive = responses["package.zip"]
        assert archive.headers["content-type"] == "application/zip"
        for artifact in ("package.sha256", "endpoint.txt", "marketplace.txt"):
            assert responses[artifact].headers["content-type"] == "text/plain; charset=utf-8"
        assert responses["endpoint.txt"].text == expected_endpoint + "\n"
        assert responses["marketplace.txt"].text == expected_marketplace + "\n"
        assert re.fullmatch(r"[0-9a-f]{64}\n", responses["package.sha256"].text)
        assert responses["package.sha256"].text == hashlib.sha256(archive.content).hexdigest() + "\n"
        repeated = client.get(prefix + "/package.zip")
        assert repeated.status_code == 200
        assert repeated.content == archive.content
        spoofed = client.get(
            prefix + "/package.zip?endpoint=https://attacker.invalid/mcp",
            headers={
                "Host": "attacker.invalid",
                "X-Forwarded-Host": "attacker.invalid",
                "Forwarded": "host=attacker.invalid;proto=http",
            },
        )
        assert spoofed.status_code == 200
        assert spoofed.content == archive.content
        with ZipFile(BytesIO(archive.content)) as package:
            assert json.loads(package.read("plugins/umbod/.mcp.json")) == {
                "mcpServers": {"umbod": {"type": "http", "url": expected_endpoint}},
            }
            for skill_name in ("umbod-connected-apps", "umbod-agent-behaviour"):
                assert package.read(f"plugins/umbod/skills/{skill_name}/SKILL.md").strip()
            canonical_skill = Path(__file__).resolve().parents[3] / "skills/integrations/run-diagnostics/SKILL.md"
            assert package.read("plugins/umbod/skills/run-diagnostics/SKILL.md") == canonical_skill.read_bytes()
            catalog_path = (
                ".agents/plugins/marketplace.json" if harness == "codex" else ".claude-plugin/marketplace.json"
            )
            assert json.loads(package.read(catalog_path))["name"] == expected_marketplace


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
@pytest.mark.parametrize("filename", ["install.sh", "install.ps1"])
def test_running_public_installer_scripts_use_instance_configuration(
    runtime_endpoints: RuntimeEndpoints, harness: str, filename: str,
) -> None:
    path = f"/api/install/v1/{harness}/{filename}"
    expected_logs_endpoint = "https://collector.runtime.invalid/otlp/v1/logs"
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=10, trust_env=False) as client:
        response = client.get(path)
        spoofed = client.get(
            path + "?base_url=https://attacker.invalid&endpoint=https://attacker.invalid/mcp&harness=unknown"
            "&logs_endpoint=https://attacker.invalid/v1/logs",
            headers={
                "Host": "attacker.invalid", "X-Forwarded-Host": "attacker.invalid",
                "X-Forwarded-Proto": "http", "Forwarded": "host=attacker.invalid;proto=http",
            },
        )
        assert response.status_code == spoofed.status_code == 200
        assert response.content == spoofed.content
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"] == f'inline; filename="umbod-{harness}-{filename}"'
        assert "set-cookie" not in response.headers
        if filename == "install.sh":
            assert response.text.startswith(
                "#!/usr/bin/env bash\nset -- --base-url https://umbod.example.invalid/api/install/v1"
                f" --harness {harness} --expected-endpoint https://mcp.umbod.example.invalid/mcp"
                f" --logs-endpoint {expected_logs_endpoint}\n"
            )
            assert response.text.rstrip().endswith('umbod_install "$@"')
        else:
            assert response.text.startswith("& {\n[CmdletBinding()]\nparam(")
            expressions = [
                "([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
                + base64.b64encode(value.encode("utf-8")).decode("ascii") + "')))"
                for value in (
                    "https://umbod.example.invalid/api/install/v1", harness, "https://mcp.umbod.example.invalid/mcp",
                    expected_logs_endpoint,
                )
            ]
            assert response.text.endswith(
                "} -BaseUrl " + expressions[0] + " -Harness " + expressions[1]
                + " -ExpectedEndpoint " + expressions[2] + " -LogsEndpoint " + expressions[3] + "\n"
            )
        assert "attacker.invalid" not in response.text
        for placeholder in ("__BASE_URL__", "__MCP_URL__", "{{"):
            assert placeholder not in response.text
        head = client.head(path)
        assert head.status_code == 200
        assert head.content == b""
        for header in ("content-type", "content-length", "content-disposition", "cache-control", "x-content-type-options"):
            assert head.headers[header] == response.headers[header]

