import base64
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


FAKE_CLIENT = '''#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path

assert not any("umbod_pat_v1_" in item for item in sys.argv)
assert "umbod_telemetry_payload" not in os.environ
assert not any("umbod_pat_v1_" in value for value in os.environ.values())
try:
    os.fstat(3)
except OSError:
    pass
else:
    sys.exit(90)
root = Path(os.environ["HOME"])
args = sys.argv[1:]
if Path(sys.argv[0]).name == "curl":
    shutil.copyfile(root / "artifacts" / args[-1].rsplit("/", 1)[-1], args[args.index("--output") + 1])
elif "--help" in args:
    sys.exit(0)
elif args[:2] == ["mcp", "get"]:
    sys.exit('No MCP server named "umbod"')
elif args[:3] == ["plugin", "marketplace", "list"]:
    sys.stdout.write("[]")
elif args[:3] == ["plugin", "marketplace", "add"]:
    (root / "destination").write_text(args[3])
elif args[:2] == ["plugin", "install"]:
    (root / "identity").write_text(args[2])
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(exist_ok=True)
    data = json.loads(settings.read_text()) if settings.exists() else {}
    if os.environ.get("SIMULATE_SETTINGS_CONFLICT"):
        data.setdefault("env", {})["OTEL_TRACES_EXPORTER"] = "otlp"
    data["enabledPlugins"] = {args[2]: True}
    settings.write_text(json.dumps(data))
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


class BashInstallation:
    def __init__(self, client: TestClient, home: Path, env: dict[str, str]) -> None:
        self.client = client
        self.home = home
        self.env = env
        self.settings = home / ".claude" / "settings.json"

    def seed(self, settings: str) -> None:
        self.settings.parent.mkdir(exist_ok=True)
        self.settings.write_text(settings)

    def run(self, payload: str | None, harness: Harness = "claude-code") -> subprocess.CompletedProcess[str]:
        response = self.client.get(f"/api/install/v1/{harness}/install.sh")
        source = response.text
        if payload is not None:
            shebang, body = source.split("\n", 1)
            source = f"{shebang}\numbod_telemetry_payload='{payload}'\n{body}"
        script = self.home / "install.sh"
        script.write_text(source)
        return subprocess.run(["bash", str(script)], env=self.env, capture_output=True, text=True, timeout=30, check=False)


@pytest.fixture
def installation(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BashInstallation:
    if os.name != "posix" or not shutil.which("bash"):
        pytest.skip("Bash installer requires a POSIX environment")
    home = tmp_path.resolve()
    commands = home / "bin"
    commands.mkdir()
    for name in ("claude", "curl"):
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
    return BashInstallation(client, home, {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
                                           "PATH": str(commands) + os.pathsep + os.environ["PATH"]})


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
