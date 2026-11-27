from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

INSTALLERS = Path(__file__).resolve().parents[2] / "api/src/umbod/rest/install/assets"
ENDPOINT = "https://example.test/mcp"
MARKETPLACE = "umbod-" + hashlib.sha256(ENDPOINT.encode()).hexdigest()[:12]
COMPLETION_ICON = "\n".join(["      |", "      |", "     /|\\", "    / | \\", "   |  |  |", "   |     |", "", "   Umbod"])


def completion_message(harness: str, *, windows: bool = False) -> str:
    harness_name = "Codex" if harness == "codex" else "Claude Code"
    codex_step = "Open or restart Codex when you are ready." if windows else "Start Codex when you are ready."
    first_step = codex_step if harness == "codex" else "Restart Claude Code."
    return (
        f"\n{COMPLETION_ICON}\n\n"
        f"Umbod plugin installed for {harness_name}. Plugin registration verified.\n\n"
        f"1. {first_step}\n"
        "2. Open /mcp and sign in if prompted.\n"
        "3. Ask your agent to discover available Umbod connected apps.\n\n"
        "Connection has not been verified. Installation does not verify access to connected apps.\n\n"
    )


STUB = '''#!PYTHON
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["INSTALLER_TEST_ROOT"])
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps([name] + args) + "\\n")
if os.environ.get("HANG_STAGE") == "help" and "--help" in args:
    time.sleep(60)
if os.environ.get("HANG_STAGE") == "registration" and args[:2] in [["plugin", "add"], ["plugin", "install"]] and "--help" not in args:
    subprocess.Popen([sys.executable, "-c", "import pathlib,sys,time; time.sleep(3); pathlib.Path(sys.argv[1]).touch()", str(root / "orphan-finished")])
    (root / "child-started").touch()
    time.sleep(60)
if name == "curl":
    if os.environ.get("FAIL_DOWNLOAD"):
        sys.exit(22)
    shutil.copyfile(root / "downloads" / args[-1].rsplit("/", 1)[-1], args[args.index("--output") + 1])
    sys.exit(0)
if "--help" in args:
    sys.exit(2 if os.environ.get("UNSUPPORTED_HARNESS") else 0)
if args[:2] == ["mcp", "list"]:
    print(json.dumps([{"name": "umbod"}] if os.environ.get("MCP_CONFLICT") else []))
    sys.exit(0)
if args[:2] == ["mcp", "get"]:
    if os.environ.get("MCP_CONFLICT"):
        print("umbod")
        sys.exit(0)
    print('No MCP server named "umbod".', file=sys.stderr)
    sys.exit(1)
state = root / (name + "-marketplaces.json")
installed_state = root / (name + "-installed.json")
if args[:2] == ["plugin", "list"]:
    installed = json.loads(installed_state.read_text()) if installed_state.exists() else []
    if name == "codex":
        if "--marketplace" not in args or args[args.index("--marketplace") + 1] == "openai-curated-remote":
            if os.environ.get("STALL_REMOTE_CATALOG"):
                time.sleep(60)
            sys.exit(8)
        marketplace = args[args.index("--marketplace") + 1]
        installed = [item for item in installed if item["pluginId"].rsplit("@", 1)[-1] == marketplace]
    if os.environ.get("DISABLED_PLUGIN"):
        for item in installed:
            item["enabled"] = False
    if os.environ.get("INVALID_PLUGIN_SOURCE"):
        for item in installed:
            item["source"]["path"] = str(root / "unverified")
            item["readFromFolder"] = str(root / "unverified")
    print(json.dumps({"installed": installed} if name == "codex" else installed))
    sys.exit(0)
if args[:3] == ["plugin", "marketplace", "list"]:
    items = json.loads(state.read_text()) if state.exists() else []
    print(json.dumps({"marketplaces": items} if name == "codex" else items))
    sys.exit(0)
if args[:3] == ["plugin", "marketplace", "add"]:
    path = pathlib.Path(args[3])
    catalog = path / (".agents/plugins/marketplace.json" if name == "codex" else ".claude-plugin/marketplace.json")
    marketplace = json.loads(catalog.read_text())["name"]
    markets = json.loads(state.read_text()) if state.exists() else []
    state.write_text(json.dumps(markets + [{"name": marketplace, "root": str(path), "path": str(path)}]))
    sys.exit(0)
if args[:2] in [["plugin", "add"], ["plugin", "install"]]:
    if os.environ.get("FAIL_REGISTRATION"):
        sys.exit(5)
    market = next(item for item in json.loads(state.read_text()) if item["name"] == args[2].rsplit("@", 1)[-1])
    plugin_root = pathlib.Path(market["root"]) / "plugins/umbod"
    installed_plugin = {
        "pluginId": args[2],
        "id": args[2],
        "enabled": True,
        "scope": "user",
        "source": {"source": "local", "path": str(plugin_root)},
        "readFromFolder": str(plugin_root),
    }
    if name == "codex":
        manifest = json.loads((plugin_root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        installed_plugin["version"] = manifest["version"]
    installed_state.write_text(json.dumps([installed_plugin]))
    sys.exit(0)
sys.exit(9)
'''


@dataclass(frozen=True)
class InstallerDriver:
    root: Path
    environment: dict[str, str]
    harness: str

    @property
    def downloads(self) -> Path:
        return self.root / "downloads"

    @property
    def installation_parent(self) -> Path:
        relative = "Library/Application Support/Umbod/plugins" if platform.system() == "Darwin" else ".local/share/umbod/plugins"
        return self.root.resolve() / "home" / relative / MARKETPLACE / self.harness

    def run(self, *arguments: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(INSTALLERS / "install.sh"), "--base-url", "https://example.test/api/install/v1", "--harness", self.harness, "--expected-endpoint", ENDPOINT, *arguments],
            env=self.environment | (environment or {}),
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def calls(self) -> list[list[str]]:
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def write_archive(self, extra: str = "", symlink: bool = False, endpoint: str = ENDPOINT, marketplace: str = MARKETPLACE, missing: str = "") -> None:
        catalog = ".agents/plugins/marketplace.json" if self.harness == "codex" else ".claude-plugin/marketplace.json"
        manifest = "plugins/umbod/" + (".codex-plugin" if self.harness == "codex" else ".claude-plugin") + "/plugin.json"
        source: str | dict[str, str] = {"source": "local", "path": "./plugins/umbod"} if self.harness == "codex" else "./plugins/umbod"
        files = {
            catalog: json.dumps({"name": marketplace, "owner": {"name": "Umbod"}, "plugins": [{"name": "umbod", "source": source, "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"}}]}),
            manifest: json.dumps({"name": "umbod", "version": "0.1.0", "skills": "./skills/", "mcpServers": "./.mcp.json"}),
            "plugins/umbod/.mcp.json": json.dumps({"mcpServers": {"umbod": {"type": "http", "url": endpoint}}}),
            "plugins/umbod/skills/run-diagnostics/SKILL.md": "Umbod run diagnostics skill",
            "plugins/umbod/LICENSE": "MIT",
        }
        if missing:
            del files[missing]
        with zipfile.ZipFile(self.downloads / "package.zip", "w") as archive:
            for name, content in files.items():
                entry = zipfile.ZipInfo(name)
                entry.external_attr = ((stat.S_IFLNK if symlink and name.endswith("LICENSE") else stat.S_IFREG) | 0o600) << 16
                archive.writestr(entry, content)
            if extra:
                archive.writestr(extra, "unexpected")
        digest = hashlib.sha256((self.downloads / "package.zip").read_bytes()).hexdigest()
        (self.downloads / "package.sha256").write_bytes((digest + "\n").encode("ascii"))


@pytest.fixture(params=["codex", "claude-code"])
def installer(tmp_path: Path, request: pytest.FixtureRequest) -> InstallerDriver:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    for name in ["curl", "codex", "claude"]:
        path = binaries / name
        path.write_text(STUB.replace("#!PYTHON", "#!" + sys.executable))
        path.chmod(0o700)
    environment = dict(os.environ) | {"PATH": str(binaries) + os.pathsep + os.environ["PATH"], "HOME": str(home), "XDG_DATA_HOME": str(home / ".local/share"), "INSTALLER_TEST_ROOT": str(tmp_path)}
    driver = InstallerDriver(tmp_path, environment, request.param)
    driver.write_archive()
    (downloads / "marketplace.txt").write_text(MARKETPLACE + "\n")
    (downloads / "endpoint.txt").write_text(ENDPOINT + "\n")
    return driver


def test_installs_verified_package_and_reruns_without_duplicate_marketplace(installer: InstallerDriver) -> None:
    first = installer.run(environment={"NO_COLOR": "1", "TERM": "dumb"})
    second = installer.run(environment={"NO_COLOR": "1", "TERM": "dumb"})
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    for result in (first, second):
        assert result.stdout.startswith("Preparing Umbod installer prerequisites...")
        assert f"Checking {installer.harness} installer prerequisites..." in result.stdout
        assert result.stdout.endswith(completion_message(installer.harness))
        assert result.stdout.count(COMPLETION_ICON) == 1
        assert result.stdout.isascii()
        assert "\x1b" not in result.stdout
        assert ENDPOINT not in result.stdout
        assert MARKETPLACE not in result.stdout
    registrations = [call for call in installer.calls() if call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call]
    assert len(registrations) == 1
    assert Path(registrations[0][4]).is_absolute()
    assert len(list(installer.installation_parent.glob("*/plugins/umbod/.mcp.json"))) == 1
    installed_package = Path(registrations[0][4])
    assert (installed_package / "plugins/umbod/skills/run-diagnostics/SKILL.md").read_text() == "Umbod run diagnostics skill"
    assert not (installer.installation_parent / ".install.lock").exists()
    installations = [call for call in installer.calls() if call[1:3] == ["plugin", "add" if installer.harness == "codex" else "install"] and "--help" not in call]
    assert len(installations) == 1
    assert "already installed" in second.stdout
    if installer.harness == "claude-code":
        assert installations[-1][-2:] == ["--scope", "user"]
    else:
        listings = [call for call in installer.calls() if call[1:3] == ["plugin", "list"]]
        assert listings == [["codex", "plugin", "list", "--json", "--marketplace", MARKETPLACE]] * 4


@pytest.mark.parametrize("url", ["http://example.test/api/install/v1", "https://user@example.test/api/install/v1", "https://example.test/api/install/v1?q=1", "https://example.test/api/install/v1#x", "https://example.test/api/install/v1;touch", "https://example.test/api/install/v1'", "https://example.test/api/install/v1\n", "http://127.0.0.1.evil.test/api/install/v1"])
def test_rejects_unsafe_transport_before_network_or_config_changes(installer: InstallerDriver, url: str) -> None:
    result = installer.run("--base-url", url)
    assert result.returncode != 0
    assert not installer.calls()
    assert not installer.installation_parent.exists()


@pytest.mark.parametrize("prefix", ["team+one", "team!one;v=2,@name:part&more=(yes)", "team\'one", 'team"one', "team+ø"])
def test_valid_endpoint_path_punctuation_is_installed_as_literal_data(installer: InstallerDriver, prefix: str) -> None:
    endpoint = f"https://example.test/{prefix}/mcp"
    marketplace = "umbod-" + hashlib.sha256(endpoint.encode()).hexdigest()[:12]
    installer.write_archive(endpoint=endpoint, marketplace=marketplace)
    (installer.downloads / "endpoint.txt").write_bytes((endpoint + "\n").encode())
    (installer.downloads / "marketplace.txt").write_bytes((marketplace + "\n").encode())
    result = installer.run("--expected-endpoint", endpoint)
    assert result.returncode == 0, result.stderr
    registrations = [call for call in installer.calls() if call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call]
    installed_mcp = Path(registrations[0][4]) / "plugins/umbod/.mcp.json"
    assert json.loads(installed_mcp.read_text())["mcpServers"]["umbod"]["url"] == endpoint


def test_apostrophe_in_endpoint_path_is_literal_data_not_shell_code(installer: InstallerDriver) -> None:
    result = installer.run("--expected-endpoint", "https://example.test/team'one/mcp")
    assert result.returncode != 0
    assert "does not match --expected-endpoint" in result.stderr
    assert "unsafe characters" not in result.stderr
    assert not installer.installation_parent.exists()


def test_home_path_with_spaces_and_unicode_is_registered_without_shell_interpretation(installer: InstallerDriver) -> None:
    home = installer.root / "home with spaces ø"
    home.mkdir()
    result = installer.run(environment={"HOME": str(home), "XDG_DATA_HOME": str(home / ".local/share")})
    assert result.returncode == 0, result.stderr
    registrations = [call for call in installer.calls() if call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call]
    assert len(registrations) == 1
    assert "home with spaces ø" in registrations[0][4]
    assert Path(registrations[0][4]).is_dir()


def test_allows_explicit_loopback_http_downloads_without_http_redirects(installer: InstallerDriver) -> None:
    result = installer.run("--base-url", "http://127.0.0.1:8000/api/install/v1")
    assert result.returncode == 0, result.stderr
    downloads = [call for call in installer.calls() if call[0] == "curl"]
    assert len(downloads) == 4
    assert all(call[call.index("--proto-redir") + 1] == "=https" for call in downloads)
    assert all("--max-time" in call and "--connect-timeout" in call for call in downloads)


def test_rejects_standalone_connection_without_download_or_mutation(installer: InstallerDriver) -> None:
    result = installer.run(environment={"MCP_CONFLICT": "1"})
    assert result.returncode != 0
    assert "standalone umbod MCP connection" in result.stderr
    assert not any(call[0] == "curl" for call in installer.calls())
    assert not installer.installation_parent.exists()


def test_rejects_unsupported_platform_before_network_or_mutation(installer: InstallerDriver) -> None:
    result = installer.run("--platform", "windows")
    assert result.returncode != 0
    assert not installer.calls()
    assert not installer.installation_parent.exists()


def test_download_failure_does_not_change_installation(installer: InstallerDriver) -> None:
    result = installer.run(environment={"FAIL_DOWNLOAD": "1"})
    assert result.returncode != 0
    assert not installer.installation_parent.exists()


def test_checksum_mismatch_does_not_change_installation(installer: InstallerDriver) -> None:
    (installer.downloads / "package.sha256").write_text("0" * 64 + "\n")
    result = installer.run()
    assert result.returncode != 0
    assert "SHA256 mismatch" in result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout
    assert not installer.installation_parent.exists()


def test_endpoint_binding_mismatch_does_not_change_installation(installer: InstallerDriver) -> None:
    (installer.downloads / "endpoint.txt").write_text("https://different.test/mcp\n")
    result = installer.run()
    assert result.returncode != 0
    assert "does not match --expected-endpoint" in result.stderr
    assert not installer.installation_parent.exists()


def test_mcp_content_mismatch_does_not_change_installation(installer: InstallerDriver) -> None:
    installer.write_archive(endpoint="https://different.test/mcp")
    result = installer.run()
    assert result.returncode != 0
    assert "MCP endpoint mismatch" in result.stderr
    assert not installer.installation_parent.exists()


@pytest.mark.parametrize("entry", ["../outside", "/absolute", "plugins/umbod/../../outside", "plugins/umbod/hooks.json", "plugins\\umbod\\evil"])
def test_rejects_unexpected_and_traversing_zip_entries(installer: InstallerDriver, entry: str) -> None:
    installer.write_archive(extra=entry)
    result = installer.run()
    assert result.returncode != 0
    assert "unsafe ZIP entries" in result.stderr
    assert not installer.installation_parent.exists()


def test_rejects_missing_skill_without_installation(installer: InstallerDriver) -> None:
    installer.write_archive(missing="plugins/umbod/skills/run-diagnostics/SKILL.md")
    result = installer.run()
    assert result.returncode != 0
    assert "unsafe ZIP entries" in result.stderr
    assert not installer.installation_parent.exists()
    assert not any(call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call for call in installer.calls())


def test_rejects_zip_symlinks(installer: InstallerDriver) -> None:
    installer.write_archive(symlink=True)
    result = installer.run()
    assert result.returncode != 0
    assert "symlinks" in result.stderr
    assert not installer.installation_parent.exists()


def test_modified_existing_installation_is_not_overwritten(installer: InstallerDriver) -> None:
    first = installer.run()
    assert first.returncode == 0, first.stderr
    license_path = next(installer.installation_parent.glob("*/plugins/umbod/LICENSE"))
    license_path.write_text("user change")
    second = installer.run()
    assert second.returncode != 0
    assert "was modified" in second.stderr
    assert COMPLETION_ICON not in second.stdout
    assert "Umbod plugin installed for" not in second.stdout
    assert "1. Restart" not in second.stdout
    assert license_path.read_text() == "user change"


def test_preexisting_lock_blocks_registration_and_remains_owned_by_other_installer(installer: InstallerDriver) -> None:
    installer.installation_parent.mkdir(parents=True)
    lock = installer.installation_parent / ".install.lock"
    lock.mkdir()
    result = installer.run()
    assert result.returncode != 0
    assert "Another installation" in result.stderr
    assert lock.is_dir()
    assert not any(call[1:4] == ["plugin", "marketplace", "add"] and "--help" not in call for call in installer.calls())


def test_symlink_destination_is_not_followed(installer: InstallerDriver) -> None:
    installer.installation_parent.mkdir(parents=True)
    digest = (installer.downloads / "package.sha256").read_text().strip()
    target = installer.root / "unrelated"
    target.mkdir()
    (installer.installation_parent / digest).symlink_to(target)
    result = installer.run()
    assert result.returncode != 0
    assert "unsafe" in result.stderr
    assert list(target.iterdir()) == []


def test_registration_failure_is_reported_and_lock_is_released(installer: InstallerDriver) -> None:
    result = installer.run(environment={"FAIL_REGISTRATION": "1"})
    assert result.returncode != 0
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout
    assert not (installer.installation_parent / ".install.lock").exists()


@pytest.mark.parametrize("other_marketplace", ["umbod-000000000000", "my-local-tools"])
def test_active_umbod_plugin_for_another_instance_is_not_replaced(installer: InstallerDriver, other_marketplace: str) -> None:
    cli = "codex" if installer.harness == "codex" else "claude"
    state = installer.root / (cli + "-installed.json")
    (installer.root / (cli + "-marketplaces.json")).write_text(json.dumps([{"name": other_marketplace, "root": str(installer.root / "other"), "path": str(installer.root / "other")}]))
    state.write_text(json.dumps([{"pluginId": "umbod@" + other_marketplace, "id": "umbod@" + other_marketplace, "enabled": True}]))
    original = state.read_bytes()
    result = installer.run()
    assert result.returncode != 0
    assert "another instance" in result.stderr
    assert not any(call[0] == "curl" for call in installer.calls())
    assert state.read_bytes() == original


def test_unmarked_existing_package_is_not_adopted(installer: InstallerDriver) -> None:
    first = installer.run()
    assert first.returncode == 0, first.stderr
    marker = next(installer.installation_parent.glob("*/.umbod-install.json"))
    marker.unlink()
    result = installer.run()
    assert result.returncode != 0
    assert "was modified" in result.stderr
    assert not marker.exists()


def test_truncated_piped_bootstrap_does_not_execute_partial_installer(installer: InstallerDriver) -> None:
    script = (INSTALLERS / "install.sh").read_text()
    partial = script[:script.index('        marker_name =')]
    result = subprocess.run(["bash", "-s", "--", "--base-url", "https://example.test/api/install/v1", "--harness", installer.harness, "--expected-endpoint", ENDPOINT], input=partial, env=installer.environment, cwd=installer.root, capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode != 0
    assert not installer.calls()
    assert not installer.installation_parent.exists()


def test_unverified_plugin_source_does_not_show_completion(installer: InstallerDriver) -> None:
    result = installer.run(environment={"INVALID_PLUGIN_SOURCE": "1"})
    assert result.returncode != 0
    assert "source could not be verified" in result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout


def test_disabled_plugin_is_not_reported_as_success(installer: InstallerDriver) -> None:
    result = installer.run(environment={"DISABLED_PLUGIN": "1"})
    assert result.returncode != 0
    assert "not enabled" in result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout


def test_codex_conflict_inspection_disables_plugin_sources_only_for_that_command(installer: InstallerDriver) -> None:
    if installer.harness != "codex":
        pytest.skip("Codex-specific effective MCP source behavior")
    result = installer.run()
    assert result.returncode == 0, result.stderr
    inspections = [call for call in installer.calls() if call[1:3] == ["mcp", "list"]]
    assert inspections == [["codex", "mcp", "list", "--json", "--disable", "plugins"]]


def test_user_writable_by_others_ancestor_is_rejected(installer: InstallerDriver) -> None:
    installer.installation_parent.parent.mkdir(parents=True)
    installer.installation_parent.parent.chmod(0o777)
    result = installer.run()
    assert result.returncode != 0
    assert "ancestors must be user-owned" in result.stderr


def test_linux_honors_absolute_xdg_data_home(installer: InstallerDriver) -> None:
    if platform.system() != "Linux":
        pytest.skip("Linux-specific XDG installation path")
    data_home = installer.root / "data"
    result = installer.run(environment={"XDG_DATA_HOME": str(data_home)})
    assert result.returncode == 0, result.stderr
    assert list((data_home / "umbod/plugins" / MARKETPLACE / installer.harness).glob("*/plugins/umbod/.mcp.json"))


def test_unsupported_harness_fails_before_downloads_or_installation(installer: InstallerDriver) -> None:
    result = installer.run(environment={"UNSUPPORTED_HARNESS": "1"})
    assert result.returncode != 0
    assert not any(call[0] == "curl" for call in installer.calls())
    assert not installer.installation_parent.exists()


def test_public_api_path_prefix_is_preserved(installer: InstallerDriver) -> None:
    result = installer.run("--base-url", "https://example.test/gateway/install/v1")
    assert result.returncode == 0, result.stderr
    downloads = [call[-1] for call in installer.calls() if call[0] == "curl"]
    assert all(url.startswith(f"https://example.test/gateway/install/v1/{installer.harness}/") for url in downloads)
    assert len(downloads) == 4


def test_missing_harness_fails_before_downloads_or_installation(installer: InstallerDriver) -> None:
    cli = "codex" if installer.harness == "codex" else "claude"
    (installer.root / "bin" / cli).unlink()
    isolated = installer.root / "prerequisites"
    isolated.mkdir()
    for command in ["bash", "python3", "curl", "shasum" if platform.system() == "Darwin" else "sha256sum"]:
        executable = installer.root / "bin" / command if command == "curl" else Path(shutil.which(command) or "")
        (isolated / command).symlink_to(executable)
    result = installer.run(environment={"PATH": str(isolated)})
    assert result.returncode != 0
    assert "Required command is missing" in result.stderr
    assert not installer.calls()
    assert not installer.installation_parent.exists()


def test_real_installed_harness_registration_and_duplicate_install_in_isolated_home(installer: InstallerDriver) -> None:
    cli = "codex" if installer.harness == "codex" else "claude"
    executable = shutil.which(cli)
    if executable is None:
        pytest.skip(f"{cli} is not installed; real duplicate behavior cannot be checked")
    wrapper = installer.root / "bin" / cli
    wrapper.unlink()
    wrapper.symlink_to(executable)
    codex_home = installer.root / "home" / ".codex"
    codex_home.mkdir()
    environment = {"CODEX_HOME": str(codex_home), "CLAUDE_CONFIG_DIR": str(installer.root / "home" / ".claude")}
    first = installer.run(environment=environment)
    second = installer.run(environment=environment)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Connection has not been verified" in second.stdout


def test_remote_codex_catalog_stall_is_bypassed_during_install_and_rerun(installer: InstallerDriver) -> None:
    if installer.harness != "codex":
        pytest.skip("Codex remote catalog behavior")
    for _ in range(2):
        result = installer.run(environment={"STALL_REMOTE_CATALOG": "1", "UMBOD_INSTALL_COMMAND_TIMEOUT": "2"})
        assert result.returncode == 0, result.stderr
        assert result.stdout.endswith(completion_message(installer.harness))
    listings = [call for call in installer.calls() if call[1:3] == ["plugin", "list"]]
    assert listings == [["codex", "plugin", "list", "--json", "--marketplace", MARKETPLACE]] * 4


def test_reserved_remote_catalog_marketplace_stops_before_any_plugin_query(installer: InstallerDriver) -> None:
    if installer.harness != "codex":
        pytest.skip("Codex reserved catalog name")
    (installer.root / "codex-marketplaces.json").write_text(json.dumps([{"name": "local-first"}, {"name": "openai-curated-remote"}]))
    result = installer.run(environment={"STALL_REMOTE_CATALOG": "1", "UMBOD_INSTALL_COMMAND_TIMEOUT": "2"})
    assert result.returncode != 0
    assert "reserved Codex remote catalog name" in result.stderr
    assert not any(call[1:3] == ["plugin", "list"] or call[0] == "curl" for call in installer.calls())
    assert not installer.installation_parent.exists()


@pytest.mark.parametrize("stage,expected", [("help", "Checking"), ("registration", "Installing")])
def test_hanging_harness_command_times_out_without_success_and_cleans_owned_state(installer: InstallerDriver, stage: str, expected: str) -> None:
    temporary = installer.root / "temporary"
    temporary.mkdir()
    started = time.monotonic()
    result = installer.run(environment={"HANG_STAGE": stage, "UMBOD_INSTALL_COMMAND_TIMEOUT": "1", "TMPDIR": str(temporary)})
    assert time.monotonic() - started < 10
    assert result.returncode != 0
    assert expected in result.stderr
    assert "timed out after 1 seconds" in result.stderr
    assert "then retry" in result.stderr
    assert COMPLETION_ICON not in result.stdout
    assert "Umbod plugin installed for" not in result.stdout
    assert "1. Restart" not in result.stdout
    assert not (installer.installation_parent / ".install.lock").exists()
    assert not list(installer.installation_parent.glob(".staging-*"))
    assert not list(temporary.iterdir())
    if stage == "registration":
        assert (installer.root / "child-started").exists()
        time.sleep(3.2)
        assert not (installer.root / "orphan-finished").exists()


@pytest.mark.parametrize("value", ["0", "301", "-1", "1.5", "abc"])
def test_invalid_command_timeout_is_rejected_before_any_command(installer: InstallerDriver, value: str) -> None:
    result = installer.run(environment={"UMBOD_INSTALL_COMMAND_TIMEOUT": value})
    assert result.returncode != 0
    assert "integer from 1 to 300" in result.stderr
    assert not installer.calls()


def test_powershell_rejects_non_windows_platform_when_available(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed; Windows installer runtime behavior is not verified")
    if platform.system() == "Windows":
        pytest.skip("This check verifies non-Windows rejection only")
    result = subprocess.run([powershell, "-NoProfile", "-File", str(INSTALLERS / "install.ps1"), "-BaseUrl", "https://example.test/api/install/v1", "-Harness", "codex", "-ExpectedEndpoint", ENDPOINT], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode != 0
    assert "Unsupported platform" in result.stderr
