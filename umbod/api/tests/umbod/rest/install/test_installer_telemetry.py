import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.core.harness_plugins.rendering import Harness


LOGS_ENDPOINT = "https://telemetry.example.test/otlp/v1/logs"
TOKEN = "umbod_pat_v1_" + "ab" * 16 + "_" + "Z" * 43
DESIRED = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": LOGS_ENDPOINT,
    "OTEL_EXPORTER_OTLP_LOGS_HEADERS": "Authorization=Bearer " + TOKEN,
    "OTEL_METRICS_EXPORTER": "none",
    "OTEL_TRACES_EXPORTER": "none",
    "OTEL_LOG_USER_PROMPTS": "0",
    "OTEL_LOG_ASSISTANT_RESPONSES": "0",
    "OTEL_LOG_TOOL_DETAILS": "0",
    "OTEL_LOG_TOOL_CONTENT": "0",
    "OTEL_LOG_RAW_API_BODIES": "0",
}


def encode(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


PAYLOAD = encode(json.dumps({"endpoint": LOGS_ENDPOINT, "token": TOKEN}))
CLAIM = "A" * 43


FAKE_CLIENT = '''#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path


def toml_value(value: object) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(json.dumps(key) + " = " + toml_value(item) for key, item in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(map(toml_value, value)) + "]"
    return json.dumps(value, ensure_ascii=False)


def codex_config_rpc(home: Path) -> None:
    import tomllib

    assert home == Path(os.environ["CODEX_HOME"])
    assert home != Path(sys.argv[0]).parent.parent / "codex-config"
    path = home / "config.toml"
    for line in sys.stdin:
        request = json.loads(line)
        method = request["method"]
        if method == "initialized":
            continue
        if method == "initialize":
            result = {"codexHome": str(home)}
        elif method == "config/read":
            assert request["params"]["includeLayers"] is True
            config = tomllib.loads(path.read_text())
            exporter = config.get("otel", {}).get("exporter")
            if isinstance(exporter, dict):
                for transport in exporter.values():
                    for name in transport.get("headers", {}):
                        transport["headers"][name] = "[redacted]"
            name = {"type": "user", "file": str(path), "profile": None}
            result = {"config": config, "origins": {key: {"name": name, "version": "1"} for key in config},
                      "layers": [{"name": name, "config": config, "version": "1"}]}
        elif method == "configRequirements/read":
            result = {"requirements": None}
        elif method == "config/batchWrite":
            params = request["params"]
            assert params["filePath"] == str(path)
            assert params["reloadUserConfig"] is False
            config = tomllib.loads(path.read_text())
            for edit in params["edits"]:
                assert edit["mergeStrategy"] == "replace"
                *parents, key = edit["keyPath"].split(".")
                table = config
                for parent in parents:
                    table = table.setdefault(parent, {})
                table[key] = edit["value"]
            path.write_text("".join(json.dumps(key) + " = " + toml_value(value) + "\\n" for key, value in config.items()))
            result = {"status": "ok", "filePath": str(path)}
        else:
            raise ValueError(method)
        sys.stdout.write(json.dumps({"id": request["id"], "result": result}) + "\\n")
        sys.stdout.flush()


assert "umbod_telemetry_payload" not in os.environ
assert "UMBOD_INSTALL_CLAIM" not in os.environ
assert not any("umbod_pat_v1_" in value for value in os.environ.values())
try:
    os.fstat(3)
except OSError:
    pass
else:
    sys.exit(90)
root = Path(os.environ["HOME"])
args = sys.argv[1:]
program = Path(sys.argv[0]).name
if program == "codex" and (not args or args[0] == "--config"):
    (root / "launch").touch()
assert not any("umbod_pat_v1_" in item for item in sys.argv)
if program == "curl":
    shutil.copyfile(root / "artifacts" / args[-1].rsplit("/", 1)[-1], args[args.index("--output") + 1])
elif "--help" in args:
    sys.exit(0)
elif args[:2] == ["mcp", "get"]:
    sys.exit('No MCP server named "umbod"')
elif args[:2] == ["mcp", "list"]:
    print("[]")
elif args[:3] == ["plugin", "marketplace", "list"]:
    marketplaces = []
    if program == "codex" and (root / "destination").exists():
        destination = Path((root / "destination").read_text())
        marketplaces.append({"name": destination.parent.parent.name, "root": str(destination),
                             "marketplaceSource": {"sourceType": "local", "source": str(destination)}})
    print(json.dumps({"marketplaces": marketplaces} if program == "codex" else []))
elif args[:3] == ["plugin", "marketplace", "add"]:
    (root / "destination").write_text(args[3])
elif args[:3] == ["plugin", "marketplace", "remove"]:
    (root / "destination").unlink()
elif args[:2] == ["plugin", "install"]:
    (root / "identity").write_text(args[2])
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(exist_ok=True)
    data = json.loads(settings.read_text()) if settings.exists() else {}
    if os.environ.get("SIMULATE_SETTINGS_CONFLICT"):
        data.setdefault("env", {})["OTEL_TRACES_EXPORTER"] = "otlp"
    data["enabledPlugins"] = {args[2]: True}
    settings.write_text(json.dumps(data))
elif args[:2] == ["plugin", "add"]:
    destination = Path((root / "destination").read_text())
    if destination.name != "a" * 64 and os.environ.get("FAIL_CODEX_UPGRADE"):
        sys.exit(1)
    if destination.name == "a" * 64 or not os.environ.get("STALE_CODEX_UPGRADE"):
        manifest = json.loads((destination / "plugins/umbod/.codex-plugin/plugin.json").read_text())
        (root / "installed-version").write_text(manifest["version"])
    (root / "identity").write_text(args[2])
elif args[:2] == ["plugin", "list"] and program == "codex":
    installed = []
    if (root / "identity").exists() and (root / "destination").exists():
        installed.append({"pluginId": (root / "identity").read_text(), "enabled": True,
                          "version": (root / "installed-version").read_text(), "source": {"source": "local", "path": (root / "destination").read_text() + "/plugins/umbod"}})
    print(json.dumps({"installed": installed}))
elif args == ["app-server", "--strict-config", "--print-startup-config"]:
    if os.environ.get("SIMULATE_CONCURRENT_EDIT"):
        path = Path(os.environ["CODEX_HOME"]) / "config.toml"
        with path.open("a") as config:
            config.write('\\nmodel = "concurrent"\\n')
    requirements = {"analytics": {"enabled": True}} if os.environ.get("SIMULATE_MANAGED_REQUIREMENTS") else None
    print(json.dumps({"configRequirements": {"requirements": requirements}}))
elif args[:4] == ["app-server", "--strict-config", "--listen", "stdio://"]:
    codex_config_rpc(root)
elif args[:2] == ["plugin", "list"]:
    if not (root / "identity").exists() or os.environ.get("SIMULATE_FAILED_VERIFICATION"):
        sys.stdout.write("[]")
    else:
        sys.stdout.write(json.dumps([{
            "id": (root / "identity").read_text(), "scope": "user", "enabled": True,
            "readFromFolder": (root / "destination").read_text() + "/plugins/umbod",
        }]))
else:
    sys.exit(91)
'''


class ClaimExchange:
    def __init__(self, url: str, requests: list[tuple[str, str, bool]]) -> None:
        self.url = url
        self.requests = requests


@pytest.fixture
def claim_exchange(tmp_path: Path) -> Iterator[ClaimExchange]:
    requests: list[tuple[str, str, bool]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            requests.append((self.path, self.headers["Authorization"], (tmp_path / "identity").exists()))
            concurrent_edit = tmp_path / "edit-on-redemption.toml"
            if concurrent_edit.is_file():
                (tmp_path / "codex-config/config.toml").write_bytes(concurrent_edit.read_bytes())
            body = json.dumps({"logs_endpoint": LOGS_ENDPOINT, "token": TOKEN}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield ClaimExchange(f"http://127.0.0.1:{server.server_port}/api/install/v1", requests)
        finally:
            server.shutdown()
            thread.join()


class BashInstallation:
    def __init__(self, client: TestClient, home: Path, env: dict[str, str], api_origin: str) -> None:
        self.client = client
        self.home = home
        self.env = env
        self.api_origin = api_origin
        self.settings = home / ".claude" / "settings.json"
        self.codex_config = Path(env["CODEX_HOME"]) / "config.toml"

    def seed(self, settings: str) -> None:
        self.settings.parent.mkdir(exist_ok=True)
        self.settings.write_text(settings)

    def run(
        self, payload: str | None, harness: Harness = "claude-code", claim_exchange: ClaimExchange | None = None,
        choice: bytes = b"\n", interactive: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if harness == "codex":
            for name in ("package.zip", "package.sha256", "marketplace.txt", "endpoint.txt"):
                (self.home / "artifacts" / name).write_bytes(self.client.get(f"/api/install/v1/codex/{name}").content)
        response = self.client.get(f"/api/install/v1/{harness}/install.sh")
        source = response.text
        if payload is not None:
            shebang, body = source.split("\n", 1)
            source = f"{shebang}\numbod_telemetry_payload='{payload}'\n{body}"
        script = self.home / "install.sh"
        env = self.env.copy()
        if claim_exchange is not None:
            source = source.replace(self.api_origin + "/api/install/v1", claim_exchange.url)
            shebang, arguments, body = source.split("\n", 2)
            source = f"{shebang}\n{arguments} --logs-endpoint {LOGS_ENDPOINT}\n{body}"
            env["UMBOD_INSTALL_CLAIM"] = CLAIM
        script.write_text(source)
        arguments = ["bash", str(script)] if claim_exchange is None else [
            shutil.which("zsh") or "bash", "-c", '(umbodScript=$(<"$1") && bash -c "$umbodScript")', "installer", str(script)
        ]
        if harness != "codex" or claim_exchange is None or not interactive:
            terminal_input = choice.decode() if not interactive else ""
            return subprocess.run(arguments, env=env, cwd=self.home, input=terminal_input, capture_output=True,
                                  text=True, timeout=30, check=False)
        import pty

        parent, terminal = pty.openpty()
        output = bytearray()

        def read_terminal() -> None:
            while True:
                try:
                    chunk = os.read(parent, 4096)
                except OSError:
                    return
                if not chunk:
                    return
                output.extend(chunk)

        reader = Thread(target=read_terminal, daemon=True)
        reader.start()
        try:
            if choice:
                os.write(parent, choice)
            attach_terminal = "import fcntl,os,sys,termios; os.setsid(); fcntl.ioctl(0, termios.TIOCSCTTY, 0); os.execvp(sys.argv[1],sys.argv[1:])"
            result = subprocess.run([sys.executable, "-c", attach_terminal, *arguments], env=env, cwd=self.home, stdin=terminal,
                                    stdout=terminal, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
        finally:
            os.close(terminal)
            reader.join(timeout=5)
            os.close(parent)
        return subprocess.CompletedProcess(arguments, result.returncode, output.decode(), result.stderr)


@pytest.fixture
def installation(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: AppConfig) -> BashInstallation:
    if os.name != "posix" or not shutil.which("bash"):
        pytest.skip("Bash installer requires a POSIX environment")
    home = tmp_path.resolve()
    commands = home / "bin"
    commands.mkdir()
    for name in ("claude", "codex", "curl"):
        executable = commands / name
        executable.write_text(FAKE_CLIENT)
        executable.chmod(0o700)
    artifacts = home / "artifacts"
    artifacts.mkdir()
    for name in ("package.zip", "package.sha256", "marketplace.txt", "endpoint.txt"):
        response = client.get(f"/api/install/v1/claude-code/{name}")
        (artifacts / name).write_bytes(response.content)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("umbod_telemetry_payload", raising=False)
    monkeypatch.delenv("UMBOD_INSTALL_CLAIM", raising=False)
    codex_home = home / "codex-config"
    codex_home.mkdir(mode=0o700)
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("CODEX_", "OTEL_"))}
    env.update(HOME=str(home), CODEX_HOME=str(codex_home), XDG_DATA_HOME=str(home / "data"),
               PATH=str(commands) + os.pathsep + os.environ["PATH"])
    return BashInstallation(client, home, env, settings.endpoints.api_base_url.rstrip("/"))


@pytest.mark.parametrize("payload", [None, PAYLOAD], ids=["public", "private"])
def test_bash_telemetry_is_optional_and_preserves_claude_settings(installation: BashInstallation, payload: str | None) -> None:
    installation.seed('{"theme":"dark","env":{"CUSTOM":"value"}}')
    result = installation.run(payload)
    assert result.returncode == 0, result.stderr
    settings = json.loads(installation.settings.read_text())
    assert settings["theme"] == "dark"
    assert list(settings["enabledPlugins"].values()) == [True]
    assert TOKEN not in result.stdout + result.stderr
    if payload is None:
        assert settings["env"] == {"CUSTOM": "value"}
        assert "telemetry settings applied" not in result.stdout
    else:
        assert settings["env"] == {"CUSTOM": "value", **DESIRED}
        assert stat.S_IMODE(installation.settings.stat().st_mode) == 0o600
        assert "Delivery has not been verified" in result.stdout


def test_bash_redeems_claim_after_verified_claude_installation(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    installation.seed('{"env":{"CUSTOM":"value"}}')
    result = installation.run(None, claim_exchange=claim_exchange)
    assert result.returncode == 0, result.stderr
    assert claim_exchange.requests == [("/api/install/v1/claude-code/telemetry/redeem", "Bearer " + CLAIM, True)]
    assert json.loads(installation.settings.read_text())["env"] == {"CUSTOM": "value", **DESIRED}
    assert CLAIM not in result.stdout + result.stderr
    assert TOKEN not in result.stdout + result.stderr


def test_bash_does_not_redeem_claim_when_plugin_verification_fails(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    installation.env["SIMULATE_FAILED_VERIFICATION"] = "1"
    result = installation.run(None, claim_exchange=claim_exchange)
    assert result.returncode != 0
    assert claim_exchange.requests == []
    assert "plugin is not enabled" in result.stderr


def test_bash_checks_claude_settings_for_conflicts_before_redeeming(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    installation.seed('{"env":{"OTEL_TRACES_EXPORTER":"otlp"}}')
    result = installation.run(None, claim_exchange=claim_exchange)
    assert result.returncode != 0
    assert claim_exchange.requests == []
    assert "Claude Code telemetry was not applied" in result.stderr


def test_bash_does_not_redeem_when_claude_settings_are_locked(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    installation.seed('{"env":{}}')
    (installation.settings.parent / ".umbod-telemetry.lock").mkdir()
    result = installation.run(None, claim_exchange=claim_exchange)
    assert result.returncode != 0
    assert claim_exchange.requests == []


def test_bash_does_not_redeem_claude_claim_for_a_different_collector(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    installation.seed(json.dumps({"env": {**DESIRED, "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://old.example.test/v1/logs"}}))
    result = installation.run(None, claim_exchange=claim_exchange)
    assert result.returncode != 0
    assert claim_exchange.requests == []


def test_bash_renews_matching_claude_telemetry_using_claim(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    header = "OTEL_EXPORTER_OTLP_LOGS_HEADERS"
    old_token = "umbod_pat_v1_" + "a" * 32 + "_" + "B" * 43
    installation.seed(json.dumps({"env": {**DESIRED, header: "Authorization=Bearer " + old_token}}))
    result = installation.run(None, claim_exchange=claim_exchange)
    assert result.returncode == 0, result.stderr
    assert len(claim_exchange.requests) == 1
    assert json.loads(installation.settings.read_text())["env"] == DESIRED


def seed_previous_codex_install(installation: BashInstallation) -> tuple[Path, Path]:
    installed = installation.run(None, "codex")
    assert installed.returncode == 0, installed.stderr
    registered = installation.home / "destination"
    latest = Path(registered.read_text())
    previous = latest.with_name("a" * 64)
    latest.rename(previous)
    marker = previous / ".umbod-install.json"
    marker.write_text(json.dumps({**json.loads(marker.read_text()), "sha256": previous.name}))
    manifest = previous / "plugins/umbod/.codex-plugin/plugin.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()), "version": "0.0.0"}))
    (installation.home / "installed-version").write_text("0.0.0")
    registered.write_text(str(previous))
    return previous, latest


def test_bash_upgrades_verified_codex_install_before_redeeming_claim(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    previous, latest = seed_previous_codex_install(installation)
    result = installation.run(None, "codex", claim_exchange, b"1\n")
    assert result.returncode == 0, result.stderr
    assert (installation.home / "destination").read_text() == str(latest)
    assert (installation.home / "installed-version").read_text() != "0.0.0"
    assert previous.is_dir()
    assert len(claim_exchange.requests) == 1


@pytest.mark.parametrize("marker_change", ["missing", "wrong_instance", "symlink"])
def test_bash_rejects_codex_upgrade_without_a_matching_marker(
    installation: BashInstallation, claim_exchange: ClaimExchange, marker_change: str,
) -> None:
    previous, _ = seed_previous_codex_install(installation)
    marker = previous / ".umbod-install.json"
    if marker_change == "missing":
        marker.unlink()
    elif marker_change == "wrong_instance":
        marker.write_text(json.dumps({**json.loads(marker.read_text()), "endpoint": "https://another.test/mcp"}))
    else:
        relocated = installation.home / "copied-marker.json"
        marker.rename(relocated)
        marker.symlink_to(relocated)
    result = installation.run(None, "codex", claim_exchange)
    assert result.returncode != 0
    assert "not a verified install" in result.stderr
    assert (installation.home / "destination").read_text() == str(previous)
    assert claim_exchange.requests == []


def test_bash_does_not_replace_a_codex_marketplace_with_additional_plugins(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    previous, _ = seed_previous_codex_install(installation)
    catalog_path = previous / ".agents/plugins/marketplace.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["plugins"].append({"name": "manual-plugin", "source": {"source": "local", "path": "./plugins/manual"}})
    catalog_path.write_text(json.dumps(catalog))
    result = installation.run(None, "codex", claim_exchange)
    assert result.returncode != 0
    assert "not a verified install" in result.stderr
    assert (installation.home / "destination").read_text() == str(previous)
    assert claim_exchange.requests == []


@pytest.mark.parametrize("failure", ["FAIL_CODEX_UPGRADE", "STALE_CODEX_UPGRADE"])
def test_bash_restores_previous_codex_registration_when_upgrade_fails(
    installation: BashInstallation, claim_exchange: ClaimExchange, failure: str,
) -> None:
    previous, _ = seed_previous_codex_install(installation)
    installation.env[failure] = "1"
    result = installation.run(None, "codex", claim_exchange)
    assert result.returncode != 0
    assert "previous Codex plugin was restored" in result.stderr
    assert (installation.home / "destination").read_text() == str(previous)
    assert (installation.home / "installed-version").read_text() == "0.0.0"
    assert claim_exchange.requests == []


def test_bash_retry_does_not_redeem_if_codex_reports_an_unexpected_version(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    installed = installation.run(None, "codex")
    assert installed.returncode == 0, installed.stderr
    (installation.home / "installed-version").write_text("0.0.0")
    result = installation.run(None, "codex", claim_exchange)
    assert result.returncode != 0
    assert "version does not match" in result.stderr
    assert claim_exchange.requests == []


EXISTING_CODEX_CONFIG = """model = "previous-model"

[features]
shell_snapshot = true

[analytics]
enabled = true

[otel]
trace_exporter = "none"
log_user_prompt = true

[otel.exporter.otlp-http]
endpoint = "https://otel.example.com/private-secret?token=query-secret"

[otel.exporter.otlp-http.headers]
Authorization = "header-secret"
X-Additional = "extra-secret"
"""


@pytest.mark.parametrize("existing", [False, True], ids=["new-config", "existing-config"])
def test_bash_saves_codex_telemetry_without_starting_codex(
    installation: BashInstallation, claim_exchange: ClaimExchange, existing: bool,
) -> None:
    config = installation.codex_config
    if existing:
        config.write_text(EXISTING_CODEX_CONFIG)
        config.chmod(0o644)
    result = installation.run(None, "codex", claim_exchange, b"1\n")
    assert result.returncode == 0, result.stderr
    assert claim_exchange.requests == [("/api/install/v1/codex/telemetry/redeem", "Bearer " + CLAIM, True)]
    assert "Choose [1-2] (default: 2)" in result.stdout
    assert "Save Umbod telemetry as my Codex default" in result.stdout
    assert "Delivery has not been verified. Codex was not started." in result.stdout
    expected = tomllib.loads(EXISTING_CODEX_CONFIG) if existing else {}
    expected.update(analytics={"enabled": False}, otel={
        "log_user_prompt": False, "log_agent_responses": False, "log_guardian_assessments": False,
        "log_sse_deltas": False, "tool_result": {"max_bytes": 0},
        "trace_exporter": "none", "metrics_exporter": "none",
        "exporter": {"otlp-http": {"endpoint": LOGS_ENDPOINT, "protocol": "json",
                                  "headers": {"Authorization": "Bearer " + TOKEN}}},
    })
    assert tomllib.loads(config.read_text()) == expected
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    backups = list(config.parent.glob("config.umbod-backup-*.toml"))
    if existing:
        assert all(value in result.stdout for value in ("https://otel.example.com", "Configured (hidden)", "Prompt logging"))
        assert len(backups) == 1
        backup, = backups
        assert backup.read_text() == EXISTING_CODEX_CONFIG
        assert stat.S_IMODE(backup.stat().st_mode) == 0o600
        assert str(backup) in result.stdout
    else:
        assert backups == []
    assert all(secret not in result.stdout + result.stderr for secret in
               (CLAIM, TOKEN, "private-secret", "query-secret", "header-secret", "extra-secret"))
    assert not (installation.home / "launch").exists()


@pytest.mark.parametrize(("choice", "interactive"), [
    (b"2\n", True), (b"\n", True), (b"1\n", False),
], ids=["decline", "default", "noninteractive"])
def test_bash_keeps_codex_configuration_without_explicit_interactive_consent(
    installation: BashInstallation, claim_exchange: ClaimExchange, choice: bytes, interactive: bool,
) -> None:
    installation.codex_config.write_text(EXISTING_CODEX_CONFIG)
    result = installation.run(None, "codex", claim_exchange, choice, interactive)
    assert result.returncode == 0, result.stderr
    assert "Plugin registration verified" in result.stdout
    assert ("Choose [1-2] (default: 2)" in result.stdout) is interactive
    assert "No Umbod telemetry was configured. Codex was not started." in result.stdout
    assert claim_exchange.requests == []
    assert installation.codex_config.read_text() == EXISTING_CODEX_CONFIG
    assert list(installation.codex_config.parent.iterdir()) == [installation.codex_config]
    assert not (installation.home / "launch").exists()


@pytest.mark.parametrize(("unsafe_setting", "reason"), [
    ("ambient", "environment overrides are set"),
    ("profile", "active configuration profile"),
    ("symlink", "user configuration could not be safely opened"),
])
def test_bash_does_not_offer_saving_codex_telemetry_with_unsafe_settings(
    installation: BashInstallation, claim_exchange: ClaimExchange, unsafe_setting: str, reason: str,
) -> None:
    config = installation.codex_config
    if unsafe_setting == "ambient":
        installation.env["OTEL_EXPORTER_OTLP_HEADERS"] = "ambient-secret"
    if unsafe_setting == "symlink":
        config.symlink_to(installation.home / "outside.toml")
    contents = 'profile = "active"\n' if unsafe_setting == "profile" else EXISTING_CODEX_CONFIG
    config.write_text(contents)
    result = installation.run(None, "codex", claim_exchange, b"1\n")
    assert result.returncode == 0, result.stderr
    assert "Choose [2] (default: 2)" in result.stdout
    assert "Save Umbod telemetry as my Codex default" not in result.stdout
    assert reason in result.stdout
    assert "ambient-secret" not in result.stdout + result.stderr
    assert claim_exchange.requests == []
    assert config.read_text() == contents
    assert config.is_symlink() is (unsafe_setting == "symlink")
    assert list(config.parent.iterdir()) == [config]
    assert not (installation.home / "launch").exists()


@pytest.mark.parametrize(("failure", "contents"), [
    ("SIMULATE_MANAGED_REQUIREMENTS", ""),
    ("SIMULATE_CONCURRENT_EDIT", '\nmodel = "concurrent"\n'),
], ids=["unverified-active-requirements", "concurrent-edit"])
def test_bash_does_not_redeem_codex_claim_when_active_configuration_cannot_be_verified(
    installation: BashInstallation, claim_exchange: ClaimExchange, failure: str, contents: str,
) -> None:
    installation.env[failure] = "1"
    config = installation.codex_config
    config.touch()
    result = installation.run(None, "codex", claim_exchange, b"1\n")
    assert result.returncode != 0
    assert "Choose [1-2] (default: 2)" in result.stdout
    assert "No Umbod telemetry token was created." in result.stderr
    assert claim_exchange.requests == []
    assert config.read_text() == contents
    assert list(config.parent.iterdir()) == [config]
    assert not (installation.home / "launch").exists()


def test_bash_preserves_concurrent_codex_edit_after_claim_redemption(
    installation: BashInstallation, claim_exchange: ClaimExchange,
) -> None:
    config = installation.codex_config
    config.write_text('model = "original"\n')
    concurrent = 'model = "concurrent"\n'
    (installation.home / "edit-on-redemption.toml").write_text(concurrent)
    result = installation.run(None, "codex", claim_exchange, b"1\n")
    assert result.returncode != 0
    assert "revoke" in result.stderr.lower()
    assert TOKEN not in result.stdout + result.stderr
    assert claim_exchange.requests == [("/api/install/v1/codex/telemetry/redeem", "Bearer " + CLAIM, True)]
    assert config.read_text() == concurrent
    assert list(config.parent.iterdir()) == [config]
    assert not (installation.home / "launch").exists()


def test_bash_renews_a_matching_umbod_telemetry_configuration(installation: BashInstallation) -> None:
    previous_token = "umbod_pat_v1_" + "c" * 32 + "_" + "d" * 43
    header = "OTEL_EXPORTER_OTLP_LOGS_HEADERS"
    installation.seed(json.dumps({"env": {**DESIRED, header: "Authorization=Bearer " + previous_token, "CUSTOM": "value"}}))
    result = installation.run(PAYLOAD)
    assert result.returncode == 0, result.stderr
    assert json.loads(installation.settings.read_text())["env"] == {**DESIRED, "CUSTOM": "value"}
    assert all(secret not in result.stdout + result.stderr for secret in (previous_token, TOKEN))


@pytest.mark.parametrize("contents", [
    '{"env":{"OTEL_TRACES_EXPORTER":"otlp"}}', '{"env":{"otel_logs_exporter":"otlp"}}',
    '{"env":{"OTEL_EXPORTER_OTLP_HEADERS":"private"}}', '{"env":{},"env":{}}', '{"env":', '{"env":[]}',
    '{"otelHeadersHelper":"helper"}',
])
def test_bash_telemetry_conflicts_and_ambiguous_settings_require_review(installation: BashInstallation, contents: str) -> None:
    installation.seed(contents)
    result = installation.run(PAYLOAD)
    assert result.returncode != 0
    assert "Review your settings manually" in result.stderr
    assert installation.settings.read_text() == contents
    assert not (installation.home / "identity").exists()


@pytest.mark.parametrize("payload", [
    "", "@", "A" * 8193,
    encode(json.dumps({"endpoint": LOGS_ENDPOINT, "token": TOKEN + "\n"})),
    encode(json.dumps({"endpoint": LOGS_ENDPOINT, "token": TOKEN, "other": "private"})),
    encode('{"endpoint": "https://ok.test/v1/logs", "endpoint": "https://evil.test/v1/logs", "token": "' + TOKEN + '"}'),
    *[encode(json.dumps({"endpoint": endpoint, "token": TOKEN})) for endpoint in [
        "http://public.test/v1/logs", "https://user:secret@public.test/v1/logs", "https://telemetry.test/v1/logs?secret",
        "https://telemetry.test/v1/logs#secret", "https://telemetry.test/v1/traces", "https://telemetry.test/%0a/v1/logs",
    ]],
])
def test_bash_invalid_private_payload_fails_without_credentials_or_settings_writes(installation: BashInstallation, payload: str) -> None:
    result = installation.run(payload)
    assert result.returncode != 0
    assert "Invalid Claude Code telemetry payload" in result.stderr
    assert TOKEN not in result.stdout + result.stderr
    assert not installation.settings.exists()


def test_bash_telemetry_accepts_loopback_http(installation: BashInstallation) -> None:
    endpoint = "http://[::1]:4318/v1/logs"
    result = installation.run(encode(json.dumps({"endpoint": endpoint, "token": TOKEN})))
    assert result.returncode == 0, result.stderr
    assert json.loads(installation.settings.read_text())["env"]["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == endpoint


def test_bash_telemetry_rejects_codex(installation: BashInstallation) -> None:
    result = installation.run(PAYLOAD, "codex")
    assert result.returncode != 0
    assert "supported only for Claude Code" in result.stderr


def test_bash_telemetry_does_not_follow_settings_symlink(installation: BashInstallation) -> None:
    target = installation.home / "outside.json"
    target.write_text('{}')
    installation.settings.parent.mkdir()
    installation.settings.symlink_to(target)
    result = installation.run(PAYLOAD)
    assert result.returncode != 0
    assert target.read_text() == '{}'
    assert installation.settings.is_symlink()


def test_bash_telemetry_does_not_ignore_claude_config_override(installation: BashInstallation) -> None:
    installation.env["CLAUDE_CONFIG_DIR"] = str(installation.home / "custom")
    result = installation.run(PAYLOAD)
    assert result.returncode != 0
    assert "manual setup when CLAUDE_CONFIG_DIR is set" in result.stderr
    assert not installation.settings.exists()


def test_bash_telemetry_is_not_written_if_plugin_registration_cannot_be_verified(installation: BashInstallation) -> None:
    installation.env["SIMULATE_FAILED_VERIFICATION"] = "1"
    result = installation.run(PAYLOAD)
    assert result.returncode != 0
    assert "plugin is not enabled" in result.stderr
    assert "env" not in json.loads(installation.settings.read_text())
    assert "telemetry settings applied" not in result.stdout


def test_bash_telemetry_rechecks_settings_after_plugin_registration(installation: BashInstallation) -> None:
    installation.env["SIMULATE_SETTINGS_CONFLICT"] = "1"
    result = installation.run(PAYLOAD)
    assert result.returncode != 0
    assert "Plugin registration verified, but Claude Code telemetry was not applied" in result.stderr
    assert json.loads(installation.settings.read_text())["env"] == {"OTEL_TRACES_EXPORTER": "otlp"}
    assert "telemetry settings applied" not in result.stdout


@pytest.fixture
def powershell(tmp_path: Path) -> list[str]:
    executable = next((path for name in ("pwsh", "pwsh.exe", "powershell.exe") if (path := shutil.which(name))), None)
    if executable:
        return [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(tmp_path / "installer.ps1")]
    if image := os.environ.get("UMBOD_TEST_POWERSHELL_DOCKER_IMAGE"):
        return ["docker", "run", "--rm", "--network", "none", "--pull=never", "-v", f"{tmp_path}:/installer:ro",
                image, "pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-File", "/installer/installer.ps1"]
    pytest.skip("PowerShell runtime is unavailable")


@pytest.mark.parametrize("payload", [PAYLOAD, encode('{"endpoint":null,"token":"' + TOKEN + '"}')], ids=["valid", "invalid"])
def test_powershell_reads_private_payload_from_script_scope(
    client: TestClient, tmp_path: Path, powershell: list[str], payload: str,
) -> None:
    source = client.get("/api/install/v1/claude-code/install.ps1").text
    source = source.replace("        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Unsupported platform. Use install.sh on macOS or Linux.' }\n", "")
    source = source.replace("            Update-ClaudeTelemetry $Telemetry $false", r"""            $Original = '{"theme":"dark","env":{"CUSTOM":"value"},"count":1.000000000000000001}'
            $Merged = [UmbodTelemetrySettings]::Merge($Original, $Telemetry)
            if ($Merged -notmatch '"count":1\.000000000000000001' -or $Merged -notmatch '"CUSTOM":"value"') { throw 'Original settings were not preserved' }
            if ((ConvertFrom-Json $Merged).env.OTEL_EXPORTER_OTLP_LOGS_HEADERS -cne $Telemetry['OTEL_EXPORTER_OTLP_LOGS_HEADERS']) { throw 'Telemetry settings were not merged' }
            foreach ($Conflict in @('{"env":{},"e\u006ev":{}}', '{"env":{"OTEL_TRACES_EXPORTER":"otlp"}}', '{"env": [1,]}')) {
                $Refused = $false
                try { $null = [UmbodTelemetrySettings]::Merge($Conflict, $Telemetry) } catch { $Refused = $true }
                if (-not $Refused) { throw 'Conflicting or ambiguous settings were not refused' }
            }
            Write-Output 'Payload validated and settings merged'
            return""")
    (tmp_path / "installer.ps1").write_text(f"$UmbodTelemetryPayload = '{payload}'\n" + source)
    result = subprocess.run(powershell, capture_output=True, text=True, timeout=60, check=False)
    assert TOKEN not in result.stdout + result.stderr
    if payload == PAYLOAD:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "Payload validated and settings merged"
    else:
        assert result.returncode != 0
        assert "Invalid Claude Code telemetry payload" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows settings publication requires native ACL and filesystem APIs")
@pytest.mark.parametrize("existing", [False, True], ids=["new-settings", "existing-settings"])
def test_windows_publishes_private_claude_settings(
    client: TestClient, tmp_path: Path, powershell: list[str], existing: bool,
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    settings = profile / ".claude" / "settings.json"
    if existing:
        settings.parent.mkdir()
        settings.write_text('{"theme":"dark","env":{"CUSTOM":"value"}}')
    source = client.get("/api/install/v1/claude-code/install.ps1").text
    source = source.replace("[Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)", "$env:USERPROFILE")
    source = source.replace("            Update-ClaudeTelemetry $Telemetry $false", """            Update-ClaudeTelemetry $Telemetry $false
            Update-ClaudeTelemetry $Telemetry $true
            return""")
    (tmp_path / "installer.ps1").write_text(f"$UmbodTelemetryPayload = '{PAYLOAD}'\n" + source)
    env = {key: value for key, value in os.environ.items() if key not in {"CLAUDE_CONFIG_DIR", "USERPROFILE"}}
    env["USERPROFILE"] = str(profile)
    result = subprocess.run(powershell, env=env, capture_output=True, text=True, timeout=60, check=False)
    assert TOKEN not in result.stdout + result.stderr
    assert result.returncode == 0, result.stderr
    expected = {"theme": "dark", "env": {"CUSTOM": "value", **DESIRED}} if existing else {"env": DESIRED}
    assert json.loads(settings.read_text(encoding="utf-8")) == expected
    assert list(settings.parent.iterdir()) == [settings]
