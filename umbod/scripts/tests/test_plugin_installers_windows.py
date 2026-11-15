from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from test_plugin_installers import COMPLETION_ICON, ENDPOINT, INSTALLERS, MARKETPLACE, STUB, InstallerDriver, completion_message

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows PowerShell installer behavior requires Windows")


class QuietArtifactHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return None


@dataclass(frozen=True)
class WindowsInstallerDriver:
    package: InstallerDriver
    powershell: str
    base_url: str

    @property
    def installation_parent(self) -> Path:
        return self.package.root / "home with spaces ø" / "AppData" / "Local" / "Umbod" / "plugins" / MARKETPLACE / self.package.harness

    def run(self, *, environment: dict[str, str] | None = None, expected_endpoint: str = ENDPOINT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(INSTALLERS / "install.ps1"), "-BaseUrl", self.base_url, "-Harness", self.package.harness, "-ExpectedEndpoint", expected_endpoint],
            cwd=self.package.root,
            env=self.package.environment | (environment or {}),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )


@pytest.fixture(params=["powershell.exe", "pwsh.exe"])
def powershell(request: pytest.FixtureRequest) -> str:
    executable = shutil.which(request.param)
    if executable is None:
        pytest.fail(f"Native Windows installer tests require {request.param}")
    return executable


@pytest.fixture(params=["codex", "claude-code"])
def windows_installer(tmp_path: Path, request: pytest.FixtureRequest, powershell: str) -> Iterator[WindowsInstallerDriver]:
    if shutil.which("curl.exe") is None:
        pytest.fail("Native Windows installer tests require curl.exe")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    home = tmp_path / "home with spaces ø"
    home.mkdir()
    local_app_data = home / "AppData" / "Local"
    local_app_data.mkdir(parents=True)
    codex_home = home / ".codex"
    codex_home.mkdir()
    configuration = home / ".claude"
    configuration.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    stub = tmp_path / "harness.py"
    stub.write_text(STUB.replace("name = pathlib.Path(sys.argv[0]).name\nargs = sys.argv[1:]", "name = sys.argv[1]\nargs = sys.argv[2:]"), encoding="utf-8")
    for command in ["codex", "claude"]:
        (binaries / (command + ".cmd")).write_text(f'@"{sys.executable}" "{stub}" {command} %*\n', encoding="utf-8")
    environment = dict(os.environ) | {
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
        "HOME": str(home),
        "USERPROFILE": str(home),
        "LOCALAPPDATA": str(local_app_data),
        "CODEX_HOME": str(codex_home),
        "CLAUDE_CONFIG_DIR": str(configuration),
        "INSTALLER_TEST_ROOT": str(tmp_path),
    }
    package = InstallerDriver(tmp_path, environment, request.param)
    package.write_archive()
    (downloads / "marketplace.txt").write_bytes((MARKETPLACE + "\n").encode())
    (downloads / "endpoint.txt").write_bytes((ENDPOINT + "\n").encode())
    package_checksum = downloads / "package.sha256"
    package_checksum.write_bytes(package_checksum.read_text().encode())
    public_root = tmp_path / "public"
    public_downloads = public_root / "api" / "install" / "v1" / request.param
    public_downloads.parent.mkdir(parents=True)
    shutil.copytree(downloads, public_downloads)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietArtifactHandler, directory=str(public_root)))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base_url = f"http://127.0.0.1:{server.server_port}/api/install/v1"
    try:
        yield WindowsInstallerDriver(package, powershell, base_url)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_windows_fresh_install_and_identical_rerun_are_verified(windows_installer: WindowsInstallerDriver) -> None:
    first = windows_installer.run(environment={"NO_COLOR": "1", "TERM": "dumb"})
    second = windows_installer.run(environment={"NO_COLOR": "1", "TERM": "dumb"})
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    for result in (first, second):
        assert f"Checking {windows_installer.package.harness} installer prerequisites..." in result.stdout
        assert f"Checking plugin command support for {'codex' if windows_installer.package.harness == 'codex' else 'claude'}..." in result.stdout
        assert f"Verifying {windows_installer.package.harness} plugin registration..." in result.stdout
        assert result.stdout.endswith(completion_message(windows_installer.package.harness))
        assert result.stdout.count(COMPLETION_ICON) == 1
        assert result.stdout.isascii()
        assert "\x1b" not in result.stdout
        assert ENDPOINT not in result.stdout
        assert MARKETPLACE not in result.stdout
    calls = windows_installer.package.calls()
    registrations = [call for call in calls if call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call]
    assert len(registrations) == 1
    assert Path(registrations[0][4]).is_absolute()
    assert len(list(windows_installer.installation_parent.glob("*/plugins/umbod/.mcp.json"))) == 1
    assert len(list(windows_installer.installation_parent.glob("*/.umbod-install.json"))) == 1
    assert not (windows_installer.installation_parent / ".install.lock").exists()
    if windows_installer.package.harness == "claude-code":
        installs = [call for call in calls if call[1:3] == ["plugin", "install"] and "--help" not in call]
        assert all(call[-2:] == ["--scope", "user"] for call in installs)
    else:
        listings = [call for call in calls if call[1:3] == ["plugin", "list"]]
        assert listings == [["codex", "plugin", "list", "--json", "--marketplace", MARKETPLACE]] * 4


@pytest.mark.parametrize("prefix", ["team+one", "team!one;v=2,@name:part&more=(yes)", "team'one", 'team"one', "team+ø"])
def test_windows_valid_endpoint_path_punctuation_is_installed_as_literal_data(windows_installer: WindowsInstallerDriver, prefix: str) -> None:
    endpoint = f"https://example.test/{prefix}/mcp"
    marketplace = "umbod-" + hashlib.sha256(endpoint.encode()).hexdigest()[:12]
    windows_installer.package.write_archive(endpoint=endpoint, marketplace=marketplace)
    public = windows_installer.package.root / "public" / "api" / "install" / "v1" / windows_installer.package.harness
    shutil.copyfile(windows_installer.package.downloads / "package.zip", public / "package.zip")
    digest = hashlib.sha256((public / "package.zip").read_bytes()).hexdigest()
    (public / "package.sha256").write_bytes((digest + "\n").encode())
    (public / "endpoint.txt").write_bytes((endpoint + "\n").encode())
    (public / "marketplace.txt").write_bytes((marketplace + "\n").encode())
    result = windows_installer.run(expected_endpoint=endpoint)
    assert result.returncode == 0, result.stdout + result.stderr
    registrations = [call for call in windows_installer.package.calls() if call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call]
    installed_mcp = Path(registrations[0][4]) / "plugins/umbod/.mcp.json"
    assert json.loads(installed_mcp.read_text())["mcpServers"]["umbod"]["url"] == endpoint


def test_windows_public_api_path_prefix_is_preserved(windows_installer: WindowsInstallerDriver) -> None:
    public = windows_installer.package.root / "public"
    shutil.copytree(public / "api", public / "gateway")
    installer = WindowsInstallerDriver(
        windows_installer.package, windows_installer.powershell,
        windows_installer.base_url.replace("/api/", "/gateway/"),
    )
    result = installer.run()
    assert result.returncode == 0, result.stdout + result.stderr


def test_windows_checksum_mismatch_prevents_installation(windows_installer: WindowsInstallerDriver) -> None:
    public_checksum = windows_installer.package.root / "public" / "api" / "install" / "v1" / windows_installer.package.harness / "package.sha256"
    public_checksum.write_bytes(("0" * 64 + "\n").encode())
    result = windows_installer.run()
    assert result.returncode != 0
    assert "SHA256 mismatch" in result.stdout + result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout
    assert not windows_installer.installation_parent.exists()


def test_windows_standalone_connection_conflict_is_non_destructive(windows_installer: WindowsInstallerDriver) -> None:
    result = windows_installer.run(environment={"MCP_CONFLICT": "1"})
    assert result.returncode != 0
    assert "standalone umbod MCP connection" in result.stdout + result.stderr
    assert not windows_installer.installation_parent.exists()
    assert not any(call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call for call in windows_installer.package.calls())


def test_windows_harness_nonzero_exit_is_reported_and_recoverable(windows_installer: WindowsInstallerDriver) -> None:
    failed = windows_installer.run(environment={"FAIL_REGISTRATION": "1"})
    assert failed.returncode != 0
    assert COMPLETION_ICON not in failed.stdout
    assert "Umbod plugin installed for" not in failed.stdout
    assert "1. Restart" not in failed.stdout
    assert not (windows_installer.installation_parent / ".install.lock").exists()
    recovered = windows_installer.run()
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert recovered.stdout.endswith(completion_message(windows_installer.package.harness))


def test_windows_expected_endpoint_mismatch_prevents_mutations(windows_installer: WindowsInstallerDriver) -> None:
    endpoint_file = windows_installer.package.root / "public" / "api" / "install" / "v1" / windows_installer.package.harness / "endpoint.txt"
    endpoint_file.write_bytes(b"https://other.example.test/mcp\n")
    result = windows_installer.run()
    assert result.returncode != 0
    assert "does not match -ExpectedEndpoint" in result.stdout + result.stderr
    assert not windows_installer.installation_parent.exists()


def test_windows_modified_content_is_not_replaced(windows_installer: WindowsInstallerDriver) -> None:
    first = windows_installer.run()
    assert first.returncode == 0, first.stdout + first.stderr
    license_path = next(windows_installer.installation_parent.glob("*/plugins/umbod/LICENSE"))
    license_path.write_text("user change", encoding="utf-8")
    result = windows_installer.run()
    assert result.returncode != 0
    assert "was modified" in result.stdout + result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout
    assert license_path.read_text(encoding="utf-8") == "user change"


def test_windows_unverified_plugin_source_does_not_show_completion(windows_installer: WindowsInstallerDriver) -> None:
    result = windows_installer.run(environment={"INVALID_PLUGIN_SOURCE": "1"})
    assert result.returncode != 0
    assert "source could not be verified" in result.stdout + result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout


def test_windows_disabled_plugin_is_not_reported_as_success(windows_installer: WindowsInstallerDriver) -> None:
    result = windows_installer.run(environment={"DISABLED_PLUGIN": "1"})
    assert result.returncode != 0
    assert "not enabled" in result.stdout + result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout


def test_windows_codex_remote_catalog_stall_is_bypassed(windows_installer: WindowsInstallerDriver) -> None:
    if windows_installer.package.harness != "codex":
        pytest.skip("Codex remote catalog behavior")
    for _ in range(2):
        result = windows_installer.run(environment={"STALL_REMOTE_CATALOG": "1"})
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.endswith(completion_message("codex"))
    listings = [call for call in windows_installer.package.calls() if call[1:3] == ["plugin", "list"]]
    assert listings == [["codex", "plugin", "list", "--json", "--marketplace", MARKETPLACE]] * 4


@pytest.mark.parametrize("other_marketplace", ["umbod-000000000000", "my-local-tools"])
def test_windows_other_local_umbod_plugin_is_not_replaced(windows_installer: WindowsInstallerDriver, other_marketplace: str) -> None:
    package = windows_installer.package
    cli = "codex" if package.harness == "codex" else "claude"
    (package.root / (cli + "-marketplaces.json")).write_text(json.dumps([{"name": other_marketplace, "root": str(package.root / "other"), "path": str(package.root / "other")}]))
    state = package.root / (cli + "-installed.json")
    state.write_text(json.dumps([{"pluginId": "umbod@" + other_marketplace, "id": "umbod@" + other_marketplace, "enabled": True}]))
    original = state.read_bytes()
    result = windows_installer.run()
    assert result.returncode != 0
    assert "another instance" in result.stdout + result.stderr
    assert state.read_bytes() == original
    assert not windows_installer.installation_parent.exists()
    assert COMPLETION_ICON not in result.stdout


def test_windows_reserved_codex_catalog_name_fails_before_plugin_queries(windows_installer: WindowsInstallerDriver) -> None:
    if windows_installer.package.harness != "codex":
        pytest.skip("Codex reserved catalog name")
    package = windows_installer.package
    (package.root / "codex-marketplaces.json").write_text(json.dumps([{"name": "local-first"}, {"name": "openai-curated-remote"}]))
    result = windows_installer.run(environment={"STALL_REMOTE_CATALOG": "1"})
    assert result.returncode != 0
    assert "reserved Codex remote catalog name" in result.stdout + result.stderr
    assert not any(call[1:3] == ["plugin", "list"] for call in package.calls())
    assert not windows_installer.installation_parent.exists()


def test_windows_unsupported_harness_fails_before_filesystem_changes(windows_installer: WindowsInstallerDriver) -> None:
    result = windows_installer.run(environment={"UNSUPPORTED_HARNESS": "1"})
    assert result.returncode != 0
    assert "Harness command failed" in result.stdout + result.stderr
    assert not windows_installer.installation_parent.exists()
