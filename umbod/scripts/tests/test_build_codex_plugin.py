from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from scripts.build_codex_plugin import (
    PLUGIN_VERSION,
    SKILL_PATH,
    build_package,
    main,
    marketplace_name,
    normalize_endpoint,
    render_package,
    write_package,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://umbod.test", "https://umbod.test/mcp"),
        ("https://umbod.test/mcp/", "https://umbod.test/mcp"),
        ("https://umbod.test/prefix/", "https://umbod.test/prefix/mcp"),
        ("https://umbod.test/prefix/mcp", "https://umbod.test/prefix/mcp"),
        ("http://localhost:8011", "http://localhost:8011/mcp"),
        ("http://127.0.0.1:8011/mcp", "http://127.0.0.1:8011/mcp"),
        ("http://[::1]:8011/mcp", "http://[::1]:8011/mcp"),
    ],
)
def test_endpoint_preserves_deployment_paths_and_normalizes_suffix(value: str, expected: str) -> None:
    assert normalize_endpoint(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "", "/mcp", "file:///mcp", "https://", "https://umbod.test:invalid/mcp",
        "https://[invalid/mcp", "https://user:secret@umbod.test/mcp", "https://user@umbod.test/mcp",
        "https://umbod.test/mcp?token=secret", "https://umbod.test/mcp?", "https://umbod.test/mcp#secret",
        "https://umbod.test/mcp#", " https://umbod.test/mcp", "https://umbod.test/\nmcp",
        "https://umbod.test/\x00mcp", "http://umbod.test/mcp", "http://localhost.evil.test/mcp",
        "https://${UMBOD_HOST}/mcp", "https://umbod.test\\@other.test/mcp",
    ],
)
def test_invalid_or_credential_bearing_endpoint_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_endpoint(value)


def test_marketplace_identity_is_stable_per_endpoint_and_distinguishes_deployments() -> None:
    assert marketplace_name("https://one.test/") == marketplace_name("https://one.test/mcp")
    assert marketplace_name("https://one.test") != marketplace_name("https://two.test")


def test_package_wires_mcp_and_canonical_skill_without_credentials() -> None:
    files = render_package("https://umbod.test/team/mcp", "canonical skill", "license")
    catalog = json.loads(files[".agents/plugins/marketplace.json"])
    manifest = json.loads(files["plugins/umbod/.codex-plugin/plugin.json"])
    mcp = json.loads(files["plugins/umbod/.mcp.json"])
    assert catalog["name"] == marketplace_name("https://umbod.test/team/mcp")
    assert catalog["plugins"][0]["source"] == {"source": "local", "path": "./plugins/umbod"}
    assert catalog["plugins"][0]["policy"] == {"installation": "AVAILABLE", "authentication": "ON_USE"}
    assert manifest["version"] == PLUGIN_VERSION
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert mcp == {"mcpServers": {"umbod": {"type": "http", "url": "https://umbod.test/team/mcp"}}}
    assert files["plugins/umbod/skills/umbod-connected-apps/SKILL.md"] == "canonical skill"
    assert files["plugins/umbod/LICENSE"] == "license"


@pytest.mark.parametrize(("skill", "license_text"), [("", "license"), ("skill", " ")])
def test_package_rejects_missing_distribution_content(skill: str, license_text: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        render_package("https://umbod.test", skill, license_text)


def test_build_copies_the_skill_source_and_preserves_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "marketplace"
    name = build_package("https://umbod.test", destination)
    assert name == marketplace_name("https://umbod.test")
    assert (destination / "plugins/umbod/skills/umbod-connected-apps/SKILL.md").read_text() == SKILL_PATH.read_text()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        build_package("https://different.test", destination)
    assert sentinel.read_text() == "keep"
    assert json.loads((destination / "plugins/umbod/.mcp.json").read_text())["mcpServers"]["umbod"]["url"] == "https://umbod.test/mcp"


@pytest.mark.parametrize("entry", ["../escape", "/absolute"])
def test_package_writer_rejects_paths_outside_destination(tmp_path: Path, entry: str) -> None:
    destination = tmp_path / "marketplace"
    with pytest.raises(ValueError, match="inside the destination"):
        write_package(destination, {entry: "content"})
    assert not destination.exists()


def test_cli_prints_quoted_install_commands_without_executing_them(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "user's marketplace"
    assert main(["--endpoint", "https://umbod.test", "--output", str(destination)]) == 0
    output = capsys.readouterr().out
    assert "'\"'\"'" in output
    assert f"codex plugin add umbod@{marketplace_name('https://umbod.test')}" in output
    assert "codex mcp login umbod" in output


def test_cli_rejects_secret_url_without_creating_output_or_echoing_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "marketplace"
    with pytest.raises(SystemExit) as caught:
        main(["--endpoint", "https://umbod.test/mcp?token=private-token", "--output", str(destination)])
    assert caught.value.code == 1
    assert "private-token" not in capsys.readouterr().err
    assert not destination.exists()


def loaded_codex_skills(directory: Path, environment: dict[str, str]) -> list[dict[str, object]]:
    with subprocess.Popen(
        ["codex", "app-server"], cwd=directory, env=environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    ) as process:
        assert process.stdout is not None
        assert process.stdin is not None
        responses: queue.Queue[dict[str, object]] = queue.Queue()
        output = process.stdout
        input_stream = process.stdin

        def read_responses() -> None:
            for line in output:
                response = json.loads(line)
                assert isinstance(response, dict)
                responses.put(response)

        reader = threading.Thread(target=read_responses, daemon=True)
        reader.start()

        def send(message: dict[str, object]) -> None:
            input_stream.write(json.dumps(message) + "\n")
            input_stream.flush()

        def receive(identifier: int) -> dict[str, object]:
            while True:
                response = responses.get(timeout=15)
                if response.get("id") == identifier:
                    assert "error" not in response, response
                    result = response["result"]
                    assert isinstance(result, dict)
                    return result

        try:
            send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "umbod-plugin-test", "version": "1.0"}}})
            receive(1)
            send({"method": "initialized"})
            send({"id": 2, "method": "skills/list", "params": {"cwds": [str(directory)], "forceReload": True}})
            result = receive(2)
            entries = result["data"]
            assert isinstance(entries, list)
            assert all(not entry["errors"] for entry in entries)
            return [skill for entry in entries for skill in entry["skills"]]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=5)


@pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is required for package-loader integration")
def test_codex_installs_generated_plugin_and_loads_its_http_server(tmp_path: Path) -> None:
    destination = tmp_path / "marketplace"
    endpoint = "http://127.0.0.1:18011/team/mcp"
    name = build_package(endpoint, destination)
    home = tmp_path / "codex-home"
    home.mkdir()
    environment = {**os.environ, "CODEX_HOME": str(home)}

    def codex(*arguments: str) -> object:
        completed = subprocess.run(
            ["codex", *arguments, "--json"], cwd=tmp_path, env=environment,
            check=True, capture_output=True, text=True, timeout=30,
        )
        return json.loads(completed.stdout)

    codex("plugin", "marketplace", "add", str(destination))
    codex("plugin", "add", f"umbod@{name}")
    server = codex("mcp", "get", "umbod")
    assert isinstance(server, dict)
    assert server["enabled"] is True
    assert server["transport"]["url"] == endpoint
    assert server["transport"]["type"] == "streamable_http"
    listing = codex("plugin", "list", "--marketplace", name)
    assert isinstance(listing, dict)
    assert len(listing["installed"]) == 1
    plugin = listing["installed"][0]
    assert plugin["pluginId"] == f"umbod@{name}"
    assert plugin["installed"] is True
    assert plugin["enabled"] is True
    skills = loaded_codex_skills(tmp_path, environment)
    connected_apps = [skill for skill in skills if skill["name"] == "umbod:umbod-connected-apps"]
    assert len(connected_apps) == 1
    assert connected_apps[0]["enabled"] is True
    assert connected_apps[0]["pluginId"] == f"umbod@{name}"
    codex("plugin", "remove", f"umbod@{name}")
    codex("plugin", "marketplace", "remove", name)
    assert codex("mcp", "list") == []
    assert (destination / "plugins/umbod/.mcp.json").is_file()
