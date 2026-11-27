#!/usr/bin/env bash
umbod_install() (
    set -eu
    printf '%s\n' 'Preparing Umbod installer prerequisites...'
    command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'Python 3 is required. Install Python 3 and retry.' >&2; exit 1; }
    if [ "${umbod_telemetry_payload+x}" ]; then
        set +x
        if [ "${#umbod_telemetry_payload}" -gt 8192 ]; then
            printf '%s\n' 'Umbod installation stopped: Invalid Claude Code telemetry payload.' >&2
            exit 1
        fi
        exec 3<<<"$umbod_telemetry_payload"
        unset umbod_telemetry_payload
    else
        exec 3</dev/null
    fi
    if [ "${UMBOD_INSTALL_CLAIM+x}" ]; then
        set +x
        exec 4<<<"$UMBOD_INSTALL_CLAIM"
        unset UMBOD_INSTALL_CLAIM
        exec 5<&0
    else
        exec 4</dev/null
    fi
    local python=python3 previous='' argument candidate
    for argument in "$@"; do
        if { [ "$previous" = --harness ] && [ "$argument" = codex ]; } || [ "$argument" = --harness=codex ]; then
            for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
                if "$candidate" -c 'import tomllib' >/dev/null 2>&1; then
                    python=$candidate
                    break
                fi
            done
            break
        fi
        previous=$argument
    done
    "$python" - "$@" <<'PY'
import argparse
import atexit
import copy
import base64
import hashlib
import ipaddress
import json
import os
import platform
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from http.client import HTTPException
from pathlib import Path
from typing import Callable
from typing import Iterator
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def fail(message: str) -> None:
    raise ValueError(message)


def validate_url(value: str) -> str:
    if not value or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        fail("URL must not contain whitespace or control characters")
    if any(character in value for character in ('\\', '$', '{', '}', '?', '#')):
        fail("URL must not contain placeholders, backslashes, a query, or a fragment")
    parsed = urlsplit(value)
    host = parsed.hostname
    if not host or parsed.scheme not in {"https", "http"} or parsed.username is not None or parsed.password is not None:
        fail("An absolute HTTPS URL is required")
    parsed.port
    if parsed.scheme == "http":
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host.lower() == "localhost"
        if not loopback:
            fail("HTTP is allowed only for loopback hosts")
    return value


def command_timeout() -> int:
    value = os.environ.get("UMBOD_INSTALL_COMMAND_TIMEOUT", "45")
    if not re.fullmatch(r"[0-9]{1,3}", value) or not 1 <= int(value) <= 300:
        fail("UMBOD_INSTALL_COMMAND_TIMEOUT must be an integer from 1 to 300 seconds")
    return int(value)


def execute(arguments: list, stage: str, timeout: int, capture: bool = True) -> subprocess.CompletedProcess:
    print(stage + "...", flush=True)
    with subprocess.Popen(arguments, text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            fail(stage + " timed out after " + str(timeout) + " seconds. Check the harness configuration and connectivity, then retry.")
        return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)


def run(arguments: list, stage: str, capture: bool = True, timeout: int = 0) -> str:
    result = execute(arguments, stage, timeout or command_timeout(), capture)
    if result.returncode:
        fail(stage + " failed. Check prerequisites and the harness configuration, then retry.")
    return result.stdout if capture else ""


def fetch(url: str, destination: Path) -> None:
    run(["curl", "-fsSL", "--proto", "=https,http", "--proto-redir", "=https", "--max-redirs", "3", "--connect-timeout", "10", "--max-time", "120", "--max-filesize", "10485760", "--output", str(destination), url], "Downloading " + destination.name, timeout=125)


def read_line(path: Path, pattern: str) -> str:
    data = path.read_bytes()
    if len(data) > 2048:
        fail("Installer metadata is too large")
    value = data.decode("utf-8")
    if not re.fullmatch(pattern + r"\n", value):
        fail("Invalid installer metadata: " + path.name)
    return value[:-1]


def ensure_owned_directory(path: Path, boundary: Path) -> None:
    for ancestor in reversed((path,) + tuple(path.parents)):
        if ancestor.is_symlink():
            fail("Refusing a symbolic-link installation directory")
        if ancestor == boundary or boundary in ancestor.parents:
            if ancestor.exists() and (ancestor.stat().st_uid != os.getuid() or ancestor.stat().st_mode & 0o022):
                fail("Installation directory ancestors must be user-owned and not writable by others")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
        fail("Installation directory must be user-owned and not writable by others")


def distinct_object(pairs: list) -> dict:
    keys = {key.casefold() for key, _ in pairs}
    if len(keys) != len(pairs):
        fail("Ambiguous JSON object")
    return dict(pairs)


def parse_json(text: str) -> object:
    return json.loads(text, object_pairs_hook=distinct_object, parse_constant=fail)


def telemetry_settings(harness: str) -> dict:
    with os.fdopen(3, "rb") as source:
        encoded = source.read(8194)
    if not encoded:
        return {}
    if harness != "claude-code":
        fail("The telemetry installer hook is supported only for Claude Code")
    try:
        if not encoded.endswith(b"\n"):
            fail("Invalid encoding")
        encoded = encoded[:-1]
        if not 0 < len(encoded) <= 8192:
            fail("Invalid size")
        decoded = base64.b64decode(encoded, validate=True)
        if base64.b64encode(decoded) != encoded:
            fail("Noncanonical encoding")
        payload = parse_json(decoded.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"endpoint", "token"}:
            fail("Unexpected keys")
        endpoint, token = validate_telemetry_credentials(payload["endpoint"], payload["token"])
    except (ValueError, OverflowError, RecursionError):
        fail("Invalid Claude Code telemetry payload")
    return claude_settings(endpoint, token)


def validate_logs_endpoint(endpoint: object) -> str:
    if not isinstance(endpoint, str) or len(endpoint) > 2048 or not re.fullmatch(r"[A-Za-z0-9:/._~!&'()*+,;=@%\[\]-]+", endpoint):
        fail("Invalid endpoint")
    if re.search(r"%(?:[01][0-9a-f]|7f)|%(?![0-9a-f]{2})", endpoint, re.IGNORECASE):
        fail("Invalid URI encoding")
    parsed = urlsplit(validate_url(endpoint))
    if not re.fullmatch(r"(?:\[[A-Fa-f0-9:.]+\]|[A-Za-z0-9.-]+)(?::[0-9]+)?", parsed.netloc) or not parsed.path.endswith("/v1/logs"):
        fail("Invalid logs URL")
    return endpoint


def validate_telemetry_credentials(endpoint: object, token: object) -> tuple:
    if not isinstance(token, str) or not re.fullmatch(r"umbod_pat_v1_[0-9a-f]{32}_[A-Za-z0-9_-]{43}", token):
        fail("Invalid token")
    return validate_logs_endpoint(endpoint), token


def claude_settings(endpoint: str, token: str) -> dict:
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": endpoint,
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS": "Authorization=Bearer " + token,
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_TRACES_EXPORTER": "none",
        "OTEL_LOG_USER_PROMPTS": "0",
        "OTEL_LOG_ASSISTANT_RESPONSES": "0",
        "OTEL_LOG_TOOL_DETAILS": "0",
        "OTEL_LOG_TOOL_CONTENT": "0",
        "OTEL_LOG_RAW_API_BODIES": "0",
    }


class ClaimRedemptionError(ValueError):
    pass


class RejectClaimRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> None:
        fail("Unexpected telemetry setup redirect")


def installation_claim() -> str:
    with os.fdopen(4, "r", encoding="ascii") as source:
        claim = source.read(45)
    if not claim:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}\n", claim):
        fail("Invalid telemetry setup code. Copy a fresh install command from Umbod.")
    return claim[:-1]


def redeem_claim(base: str, harness: str, claim: str, expected_endpoint: str) -> tuple:
    try:
        request = Request(
            base + "/" + harness + "/telemetry/redeem",
            data=b"",
            headers={"Authorization": "Bearer " + claim, "Accept": "application/json"},
            method="POST",
        )
        with build_opener(RejectClaimRedirect()).open(request, timeout=15) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                fail("Unexpected response")
            body = response.read(4097)
        payload = parse_json(body.decode("utf-8"))
        if len(body) > 4096 or not isinstance(payload, dict) or set(payload) != {"logs_endpoint", "token"}:
            fail("Unexpected credentials")
        endpoint, token = validate_telemetry_credentials(payload["logs_endpoint"], payload["token"])
        if endpoint != expected_endpoint:
            fail("Unexpected telemetry destination")
        return endpoint, token
    except (ValueError, OSError, HTTPException, OverflowError, RecursionError):
        raise ClaimRedemptionError("Plugin registration verified, but telemetry setup did not complete. Copy a fresh install command from Umbod, or restart normally without telemetry.") from None


def codex_rpc(home: Path, working: Path, calls: dict) -> dict:
    environment = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home), "CODEX_HOME": str(home),
                   "XDG_CONFIG_HOME": str(home), "XDG_DATA_HOME": str(home), "XDG_CACHE_HOME": str(home),
                   "TMPDIR": str(working)}
    command = ["codex", "app-server", "--strict-config", "--listen", "stdio://"]
    for field in ("log_dir", "sqlite_home"):
        command.extend(("--config", field + "=" + json.dumps(str(working))))
    requests = [
        {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "umbod-installer", "version": "1"}}},
        {"method": "initialized"},
        *({"id": identifier, "method": method, "params": params} for identifier, (method, params) in calls.items()),
    ]
    with subprocess.Popen(command, cwd=working, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, start_new_session=True, umask=0o077) as process:
        try:
            process.stdin.write(b"".join(json.dumps(request).encode() + b"\n" for request in requests))
            process.stdin.flush()
            deadline = time.monotonic() + 15
            responses = {}
            pending = b""
            received = 0
            while responses.keys() != {1, *calls}:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                    fail("Configuration inspection timed out")
                chunk = os.read(process.stdout.fileno(), 16384)
                received += len(chunk)
                if not chunk or received > 4194304:
                    fail("Invalid configuration response")
                lines = (pending + chunk).split(b"\n")
                pending = lines.pop()
                for line in lines:
                    message = parse_json(line.decode("utf-8"))
                    identifier = message.get("id")
                    if identifier in {1, *calls}:
                        responses[identifier] = message["result"]
            if Path(responses[1]["codexHome"]) != home:
                fail("The active Codex home could not be verified")
            return responses
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)


def has_foreground_terminal() -> bool:
    try:
        return os.isatty(1) and os.tcgetpgrp(5) == os.getpgrp()
    except OSError:
        return False


class CodexTelemetryPreflightError(ValueError):
    pass


def inspect_codex_telemetry(home: Path, working: Path, cwd: Path) -> tuple:
    responses = codex_rpc(home, working, {
        2: ("config/read", {"includeLayers": True, "cwd": str(cwd)}),
        3: ("configRequirements/read", {}),
    })
    config = responses[2]["config"]
    requirements = responses[3]["requirements"]
    if requirements is not None and (requirements.get("otel") is not None or requirements.get("analytics") is not None):
        raise CodexTelemetryPreflightError("Codex policy manages telemetry settings.")
    if config.get("profile") is not None:
        raise CodexTelemetryPreflightError("Codex has an active configuration profile. The installer cannot verify that saving a user default would take effect.")
    layers = responses[2]["layers"]
    origins = responses[2]["origins"]
    target = {"type": "user", "file": str(home / "config.toml"), "profile": None}
    if not isinstance(layers, list) or not isinstance(origins, dict):
        fail("The active Codex configuration layers could not be verified.")
    user_layers = []
    known_layers = {"packagedDefaults", "mdm", "system", "enterpriseManaged", "project", "sessionFlags",
                    "legacyManagedConfigTomlFromFile", "legacyManagedConfigTomlFromMdm"}
    for layer in layers:
        name = layer["name"]
        settings = layer["config"]
        if not isinstance(settings, dict) or not isinstance(layer["version"], str) or has_codex_headers_helper(settings):
            fail("Umbod cannot verify a Codex configuration layer.")
        if name == target:
            user_layers.append(settings)
        elif name["type"] not in known_layers:
            fail("The active Codex user configuration path could not be verified.")
        elif any(settings.get(key) is not None for key in ("otel", "analytics")):
            fail("Umbod cannot override project, managed, or other non-user Codex telemetry settings.")
    if len(user_layers) != 1:
        fail("The active Codex user configuration path could not be verified.")
    for key, origin in origins.items():
        if key.split(".")[0] in {"otel", "analytics"} and origin["name"] != target:
            fail("The source of the Codex telemetry settings could not be verified.")
    if has_codex_headers_helper(config) or has_codex_headers_helper(requirements or {}):
        fail("Umbod cannot safely override a Codex telemetry headers helper.")
    otel = config.get("otel")
    analytics = config.get("analytics")
    if (otel is not None) != ("otel" in user_layers[0]) or (analytics is not None) != ("analytics" in user_layers[0]):
        fail("The source of the Codex telemetry settings could not be verified.")
    validate_codex_exporters(otel)
    return config, layers, requirements


def has_codex_headers_helper(settings: dict) -> bool:
    return any(value is not None and "headershelper" in key.lower().replace("_", "").replace("-", "") for key, value in settings.items())


def validate_codex_exporters(otel: object) -> None:
    if otel is None:
        return
    replaced_fields = {"exporter", "trace_exporter", "metrics_exporter", "log_user_prompt", "log_agent_responses",
                       "log_guardian_assessments", "log_sse_deltas", "tool_result"}
    tool_result = otel.get("tool_result")
    if ((tool_result is not None and (not isinstance(tool_result, dict) or set(tool_result) - {"max_bytes"}))
            or any(value is not None for key, value in otel.items() if key not in replaced_fields)):
        fail("Umbod cannot safely override additional Codex telemetry settings.")
    for key in ("exporter", "trace_exporter", "metrics_exporter"):
        if not can_replace_codex_exporter(otel.get(key)):
            fail("Umbod cannot safely override an unrecognized Codex exporter.")


def can_replace_codex_exporter(exporter: object) -> bool:
    if exporter in (None, "none", "statsig", "stdout"):
        return True
    if not isinstance(exporter, dict) or len(exporter) != 1:
        return False
    kind, settings = next(iter(exporter.items()))
    if kind not in {"otlp-http", "otlp-grpc"} or not isinstance(settings, dict):
        return False
    if any(value is not None for key, value in settings.items() if key not in {"endpoint", "protocol", "headers"}):
        return False
    if not isinstance(settings.get("endpoint"), str) or settings.get("protocol") not in (None, "json", "binary"):
        return False
    headers = settings.get("headers")
    return headers is None or (isinstance(headers, dict) and all(isinstance(value, str) for value in headers.values()))


def telemetry_destination(endpoint: object) -> str:
    if not isinstance(endpoint, str):
        return "Configured (hidden)"
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parsed.scheme in {"http", "https"} and re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[A-Fa-f0-9:.]+\])", host):
            default_port = 443 if parsed.scheme == "https" else 80
            port = f":{parsed.port}" if parsed.port is not None and parsed.port != default_port else ""
            origin = f"{parsed.scheme}://{host}{port}"
            if len(origin) <= 88:
                return origin
    except ValueError:
        pass
    return "Configured (hidden)"


def telemetry_switch(value: object) -> str:
    return "Enabled" if value is True else "Disabled" if value is False else "Default"


def codex_telemetry_summary(otel: dict, analytics: dict) -> tuple:
    exporter = otel.get("exporter")
    if isinstance(exporter, dict) and len(exporter) == 1 and next(iter(exporter)) in {"otlp-http", "otlp-grpc"}:
        settings = next(iter(exporter.values()))
        destination = telemetry_destination(settings.get("endpoint"))
        authentication = "Configured (hidden)" if settings.get("headers") else "None"
    elif exporter in (None, "none", "stdout", "statsig"):
        destination = {None: "Default", "none": "Disabled", "stdout": "Standard output", "statsig": "Statsig"}[exporter]
        authentication = "Default" if exporter in (None, "statsig") else "None"
    else:
        raise ValueError
    tool_limit = (otel.get("tool_result") or {}).get("max_bytes")
    return (
        ("Logs destination", destination), ("Authentication", authentication),
        ("Traces", "Disabled" if otel.get("trace_exporter") == "none" else "Configured" if otel.get("trace_exporter") else "Default"),
        ("Metrics", "Disabled" if otel.get("metrics_exporter") == "none" else "Configured" if otel.get("metrics_exporter") else "Default"),
        ("Prompt logging", telemetry_switch(otel.get("log_user_prompt"))),
        ("Response logging", telemetry_switch(otel.get("log_agent_responses"))),
        ("Guardian logging", telemetry_switch(otel.get("log_guardian_assessments"))),
        ("SSE delta logging", telemetry_switch(otel.get("log_sse_deltas"))),
        ("Tool-result logging", "Default" if tool_limit is None else "Disabled" if tool_limit == 0 else "Enabled"),
        ("Codex analytics", telemetry_switch(analytics.get("enabled"))),
    )


def choose_codex_telemetry(reason: str, summary: tuple, endpoint: str, target: Path) -> bool:
    print("Umbod plugin installed and verified.", flush=True)
    if not has_foreground_terminal():
        print("No Umbod telemetry was configured. Codex was not started.", flush=True)
        return False
    if reason:
        print(reason, flush=True)
    if summary:
        current_width = max(32, *(len(current) for _, current in summary))
        print(f"\n  {'':20} {'Current':{current_width}}  With Umbod")
        proposed = (telemetry_destination(endpoint), "New Umbod token") + ("Disabled",) * 8
        for (label, current), replacement in zip(summary, proposed):
            print(f"  {label:20} {current:{current_width}}  {replacement}")
    if not reason:
        print("\nUmbod logs endpoint: " + endpoint)
        print("Codex user configuration: " + json.dumps(str(target)))
        print("Saving replaces the entire user telemetry section, including any custom headers, TLS settings, environment label, span attributes, and tracestate.")
        print("The Umbod token expires after 30 days.")
        print("The token is stored in plaintext in a user-only TOML file. Keep this file and any backups out of shared storage, sync, and version control.")
        print("To undo, restore the protected backup if there were no later edits, or remove the Umbod settings manually. Revoke the token in Umbod.")
        print("\n  1) Save Umbod telemetry as my Codex default")
    print("  2) Finish without configuring Umbod telemetry or starting Codex")
    print(f"Choose [{'1-2' if not reason else '2'}] (default: 2): ", end="", flush=True)
    try:
        with os.fdopen(os.dup(5), "r", encoding="utf-8", errors="replace") as terminal:
            return terminal.readline(32).strip() == "1" and not reason and has_foreground_terminal()
    except (OSError, KeyboardInterrupt):
        return False


def codex_otel(endpoint: str, token: str) -> dict:
    return {
        "log_user_prompt": False,
        "log_agent_responses": False,
        "log_guardian_assessments": False,
        "log_sse_deltas": False,
        "tool_result": {"max_bytes": 0},
        "trace_exporter": "none",
        "metrics_exporter": "none",
        "exporter": {"otlp-http": {"endpoint": endpoint, "protocol": "json", "headers": {"Authorization": "Bearer " + token}}},
    }


def codex_home() -> Path:
    if any(key.upper().startswith(("OTEL_", "CODEX_")) and key != "CODEX_HOME" for key in os.environ):
        raise CodexTelemetryPreflightError("Codex or OpenTelemetry environment overrides are set. Run the installer in a shell without those overrides.")
    default_home = Path.home() / ".codex"
    home = Path(os.environ.get("CODEX_HOME", str(default_home)))
    cwd = Path.cwd()
    if any(os.path.lexists(path / ".env") for path in (home, cwd, *cwd.parents)):
        raise CodexTelemetryPreflightError("A .env file may affect Codex settings. If it belongs to this project, rerun from a directory outside the project.")
    for ancestor in (cwd, *cwd.parents):
        project = ancestor / ".codex"
        if project not in {home, default_home} and (project.is_symlink() or os.path.lexists(project / "config.toml")):
            raise CodexTelemetryPreflightError("A project Codex configuration is present. Rerun from a directory outside the project to save the user default.")
    return home


def read_codex_file(directory: int) -> tuple:
    try:
        descriptor = os.open("config.toml", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return b"", None
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o022:
            fail("Unsafe Codex config.toml")
        require_no_macos_acl_grants(source.fileno())
        data = source.read(1048577)
        current = os.fstat(source.fileno())
        if len(data) > 1048576 or codex_file_identity(current) != codex_file_identity(info):
            fail("Invalid or changing Codex config.toml")
        return data, codex_file_identity(info)


def codex_file_identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def open_codex_home(home: Path) -> Iterator[int]:
    directory = open_owned_path(home)
    try:
        yield directory
    finally:
        os.close(directory)


def write_private_codex_file(directory: int, contents: bytes, prefix: str) -> str:
    name = prefix + os.urandom(16).hex() + ".toml"
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as target:
            os.fchmod(target.fileno(), 0o600)
            require_no_macos_acl_grants(target.fileno())
            target.write(contents)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        os.unlink(name, dir_fd=directory)
        raise
    return name


def parse_codex_toml(source: bytes) -> dict:
    import tomllib
    return tomllib.loads(source.decode("utf-8"))


def equivalent_codex_values(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equivalent_codex_values(value, right[key]) for key, value in left.items())
    if isinstance(left, list):
        return len(left) == len(right) and all(equivalent_codex_values(a, b) for a, b in zip(left, right))
    return repr(left) == repr(right)


def populate_codex_stage(directory: int, original: bytes) -> None:
    name = write_private_codex_file(directory, original, ".original-")
    os.replace(name, "config.toml", src_dir_fd=directory, dst_dir_fd=directory)


def stage_codex_telemetry(stage: Path, working: Path, original: bytes, desired: dict, verify_effective: bool) -> bytes:
    path = stage / "config.toml"
    with open_codex_home(stage) as directory:
        populate_codex_stage(directory, original)
        response = codex_rpc(stage, working, {4: ("config/batchWrite", {
            "edits": [
                {"keyPath": "otel", "value": desired, "mergeStrategy": "replace"},
                {"keyPath": "analytics.enabled", "value": False, "mergeStrategy": "replace"},
            ],
            "filePath": str(path), "reloadUserConfig": False,
        })})[4]
        if response["status"] != "ok" or Path(response["filePath"]) != path:
            fail("Codex could not stage the telemetry configuration")
        updated = read_codex_file(directory)[0]
    expected = copy.deepcopy(parse_codex_toml(original))
    expected["otel"] = desired
    expected.setdefault("analytics", {})["enabled"] = False
    if not equivalent_codex_values(parse_codex_toml(updated), expected):
        fail("The staged Codex file would change unrelated settings or could not be verified")
    if verify_effective:
        config, _, _ = inspect_codex_telemetry(stage, working, working)
        redacted = copy.deepcopy(desired)
        redacted["exporter"]["otlp-http"]["headers"]["Authorization"] = "[redacted]"
        if not equivalent_codex_values(without_codex_nulls(config["otel"]), redacted) or config["analytics"]["enabled"] is not False:
            fail("The staged Codex telemetry defaults could not be verified")
    return updated


def without_codex_nulls(value: object) -> object:
    if isinstance(value, dict):
        return {key: without_codex_nulls(item) for key, item in value.items() if item is not None}
    return value


def verify_codex_target(home: Path, directory: int, original: tuple) -> None:
    if codex_home() != home:
        fail("The active Codex configuration path changed")
    with open_codex_home(home) as active:
        a, b = os.fstat(active), os.fstat(directory)
        if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) or read_codex_file(active) != original:
            fail("The Codex configuration changed during installation")


def publish_codex_telemetry(home: Path, directory: int, original: tuple, updated: bytes) -> str:
    pending = write_private_codex_file(directory, updated, ".umbod-config-pending-")
    backup = ""
    published = False
    try:
        if original[1] is not None:
            backup = write_private_codex_file(directory, original[0], "config.umbod-backup-")
        verify_codex_target(home, directory, original)
        if original[1] is None:
            os.link(pending, "config.toml", src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        else:
            os.replace(pending, "config.toml", src_dir_fd=directory, dst_dir_fd=directory)
        published = True
        return backup
    finally:
        if original[1] is None or not published:
            os.unlink(pending, dir_fd=directory)
        if backup and not published:
            os.unlink(backup, dir_fd=directory)


def inspect_mirrored_codex(mirror: Path, working: Path, original: bytes) -> tuple:
    with open_codex_home(mirror) as directory:
        populate_codex_stage(directory, original)
    return inspect_codex_telemetry(mirror, working, Path.cwd())


def verify_active_codex_requirements(expected: object) -> None:
    startup = subprocess.run(["codex", "app-server", "--strict-config", "--print-startup-config"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=15, check=True)
    requirements = parse_json(startup.stdout.decode("utf-8"))["configRequirements"]["requirements"]
    if requirements != expected:
        fail("The active Codex configuration depends on managed settings")


def install_codex_telemetry(endpoint: str, redeem: Callable[[], tuple]) -> None:
    if not has_foreground_terminal():
        print("No Umbod telemetry was configured. Codex was not started.", flush=True)
        return
    errors = (ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError, RecursionError, subprocess.SubprocessError)
    target = Path.home() / ".codex/config.toml"
    summary = ()
    try:
        import tomllib
    except ImportError:
        choose_codex_telemetry("Saving Codex telemetry safely requires Python 3.11 or newer.", summary, endpoint, target)
        print("No Umbod telemetry was configured. Codex was not started.", flush=True)
        return
    root = "/private/tmp" if sys.platform == "darwin" else "/tmp"
    with tempfile.TemporaryDirectory(prefix="umbod-codex-", dir=root) as temporary:
        working = Path(temporary)
        stage = working / "home"
        mirror = working / "mirror"
        stage.mkdir(mode=0o700)
        mirror.mkdir(mode=0o700)
        blocker = "The Codex user configuration could not be safely opened. Check that the Codex home and config.toml belong to your account and aren't symlinks or writable by other users."
        try:
            home = codex_home()
            target = home / "config.toml"
            with open_codex_home(home) as directory:
                original = read_codex_file(directory)
            blocker = "Codex could not read or verify the configuration layers. Check that Codex is up to date and can start normally with these settings."
            config, layers, requirements = inspect_mirrored_codex(mirror, working, original[0])
            summary = codex_telemetry_summary(config.get("otel") or {}, config.get("analytics") or {})
            placeholder = "umbod_pat_v1_" + "0" * 32 + "_" + "A" * 43
            blocker = "Codex could not verify a preview of the new telemetry settings. Your existing configuration was not changed."
            stage_codex_telemetry(stage, working, original[0], codex_otel(endpoint, placeholder), verify_effective=True)
        except errors as error:
            if isinstance(error, CodexTelemetryPreflightError):
                blocker = str(error)
            choose_codex_telemetry(blocker, summary, endpoint, target)
            print("No Umbod telemetry was configured. Codex was not started.", flush=True)
            return
        if not choose_codex_telemetry("", summary, endpoint, target):
            print("No Umbod telemetry was configured. Codex was not started.", flush=True)
            return
        redeemed = False
        try:
            with open_codex_home(home) as directory:
                lock = ".umbod-telemetry.lock"
                os.mkdir(lock, 0o700, dir_fd=directory)
                try:
                    verify_codex_target(home, directory, original)
                    current = inspect_mirrored_codex(mirror, working, original[0])
                    if current != (config, layers, requirements):
                        fail("The Codex configuration changed")
                    verify_active_codex_requirements(requirements)
                    verify_codex_target(home, directory, original)
                    if not has_foreground_terminal():
                        fail("The installer no longer has the foreground terminal")
                    verified_endpoint, token = redeem()
                    redeemed = True
                    updated = stage_codex_telemetry(stage, working, original[0], codex_otel(verified_endpoint, token), verify_effective=False)
                    if inspect_mirrored_codex(mirror, working, original[0]) != current:
                        fail("The Codex configuration changed during installation")
                    verify_active_codex_requirements(requirements)
                    backup = publish_codex_telemetry(home, directory, original, updated)
                finally:
                    os.rmdir(lock, dir_fd=directory)
        except ClaimRedemptionError:
            raise
        except errors:
            if redeemed:
                fail("Umbod could not save Codex telemetry safely. Check the configuration and revoke the newly created token in Umbod before retrying.")
            fail("Umbod could not save Codex telemetry safely. No Umbod telemetry token was created.")
        print("Saved Umbod logs-only telemetry as the Codex default. Delivery has not been verified. Codex was not started.", flush=True)
        if backup:
            print("To undo, close Codex and restore " + json.dumps(str(home / backup)) + " over " + json.dumps(str(target)) +
                  " if there were no subsequent edits. Otherwise restore only the previous telemetry settings, keeping later edits.", flush=True)
        else:
            print("To undo, remove the new config.toml only if it is unchanged; otherwise remove only [otel] and analytics.enabled.", flush=True)
        print("Revoke the token in Umbod when undoing this setup.", flush=True)


def telemetry_key(key: str) -> bool:
    return key.upper().startswith(("OTEL_", "CLAUDE_CODE_OTEL_")) or key.upper() == "CLAUDE_CODE_ENABLE_TELEMETRY"


def read_settings(directory: int) -> tuple:
    try:
        descriptor = os.open("settings.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return b"{}", None
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o022:
            fail("Unsafe settings file")
        data = source.read(1048577)
        if len(data) > 1048576:
            fail("Oversized settings file")
        return data, (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns)


def json_object_positions(text: str, opening: int) -> dict:
    whitespace = re.compile(r"[ \r\n\t]*")
    decoder = json.JSONDecoder()
    positions = {}
    cursor = whitespace.match(text, opening + 1).end()
    while text[cursor] != "}":
        key, after_key = decoder.raw_decode(text, cursor)
        separator = whitespace.match(text, after_key).end()
        value_start = whitespace.match(text, separator + 1).end()
        positions[key] = value_start
        _, value_end = decoder.raw_decode(text, value_start)
        cursor = whitespace.match(text, value_end).end()
        if text[cursor] == ",":
            cursor = whitespace.match(text, cursor + 1).end()
    return positions


def insert_settings(text: str, opening: int, fields: dict, has_members: bool) -> str:
    addition = json.dumps(fields, ensure_ascii=True)[1:-1]
    return text[:opening + 1] + "\n  " + addition + ("," if has_members else "\n") + text[opening + 1:]


def merge_settings(text: str, desired: dict) -> str:
    settings = parse_json(text)
    if not isinstance(settings, dict) or any(
        key.casefold() == "otelheadershelper" or (key.casefold() == "env" and key != "env") for key in settings
    ):
        fail("Expected a settings object")
    env = settings.get("env", {})
    if not isinstance(env, dict):
        fail("Conflicting telemetry settings")
    header = "OTEL_EXPORTER_OTLP_LOGS_HEADERS"
    previous = env.get(header)
    rotate = (
        isinstance(previous, str)
        and previous != desired[header]
        and re.fullmatch(r"Authorization=Bearer umbod_pat_v1_[0-9a-f]{32}_[A-Za-z0-9_-]{43}", previous) is not None
        and all(env.get(key) == value for key, value in desired.items() if key != header)
    )
    if any(telemetry_key(key) and desired.get(key, object()) != value and not (rotate and key == header) for key, value in env.items()):
        fail("Conflicting telemetry settings")
    opening = len(text) - len(text.lstrip(" \r\n\t"))
    if rotate:
        env_opening = json_object_positions(text, opening)["env"]
        start = json_object_positions(text, env_opening)[header]
        _, end = json.JSONDecoder().raw_decode(text, start)
        return text[:start] + json.dumps(desired[header]) + text[end:]
    missing = {key: value for key, value in desired.items() if key not in env}
    if not missing:
        return text
    if "env" not in settings:
        return insert_settings(text, opening, {"env": missing}, bool(settings))
    return insert_settings(text, json_object_positions(text, opening)["env"], missing, bool(env))


def require_no_macos_acl_grants(descriptor: int) -> None:
    if sys.platform != "darwin":
        return
    import ctypes
    import errno

    library = ctypes.CDLL(None, use_errno=True)
    library.acl_get_fd.restype = ctypes.c_void_p
    library.acl_to_text.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    library.acl_to_text.restype = ctypes.c_void_p
    library.acl_free.argtypes = (ctypes.c_void_p,)
    acl = library.acl_get_fd(descriptor)
    if not acl:
        if ctypes.get_errno() != errno.ENOENT:
            fail("Could not inspect directory ACL")
        return
    try:
        text = library.acl_to_text(acl, None)
        if not text:
            fail("Could not inspect directory ACL")
        try:
            if re.search(rb":allow(?:,|:)", ctypes.string_at(text)):
                fail("Unexpected directory ACL grants")
        finally:
            library.acl_free(text)
    finally:
        library.acl_free(acl)


def open_owned_path(home: Path) -> int:
    if not home.is_absolute() or home.anchor != "/" or len(home.parts) < 2 or ".." in home.parts:
        fail("Unsafe home directory")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open("/", flags)
    try:
        for part in home.parts[1:]:
            info = os.fstat(directory)
            if info.st_uid not in {0, os.getuid()} or (info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)):
                fail("Unsafe home directory ancestor")
            require_no_macos_acl_grants(directory)
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        require_owned_configuration(directory)
        return directory
    except BaseException:
        os.close(directory)
        raise


def open_configuration_directory(home: Path, create: bool) -> int:
    directory = open_owned_path(home)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        try:
            config = os.open(".claude", flags, dir_fd=directory)
        except FileNotFoundError:
            if not create:
                return -1
            os.mkdir(".claude", 0o700, dir_fd=directory)
            config = os.open(".claude", flags, dir_fd=directory)
        try:
            require_owned_configuration(config)
        except BaseException:
            os.close(config)
            raise
        return config
    finally:
        os.close(directory)


def require_owned_configuration(descriptor: int) -> None:
    info = os.fstat(descriptor)
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        fail("Unsafe configuration directory")
    require_no_macos_acl_grants(descriptor)


def apply_claude_settings(desired: dict, write: bool, redeem: Callable[[], dict] = dict) -> None:
    if "CLAUDE_CONFIG_DIR" in os.environ:
        fail("Claude Code telemetry requires manual setup when CLAUDE_CONFIG_DIR is set")
    try:
        home = Path.home()
        directory = open_configuration_directory(home, create=write)
        if directory == -1:
            return
        try:
            if not write:
                merge_settings(read_settings(directory)[0].decode("utf-8"), desired)
                return
            lock = ".umbod-telemetry.lock"
            os.mkdir(lock, 0o700, dir_fd=directory)
            try:
                original = read_settings(directory)
                source = original[0].decode("utf-8")
                updated = merge_settings(source, desired)
                if redeem is not dict:
                    if read_settings(directory) != original:
                        fail("Settings changed during installation")
                    updated = merge_settings(source, redeem())
                save_settings(home / ".claude", directory, original, updated)
            finally:
                os.rmdir(lock, dir_fd=directory)
        finally:
            os.close(directory)
    except ClaimRedemptionError:
        raise
    except (ValueError, OSError, OverflowError, RecursionError, subprocess.CalledProcessError):
        if write:
            fail("Plugin registration verified, but Claude Code telemetry was not applied. Review your settings manually before retrying.")
        fail("Claude Code telemetry settings could not be safely updated. Review your settings manually before retrying.")


def save_settings(directory_path: Path, directory: int, original: tuple, updated: str) -> None:
    name = ".umbod-settings-" + os.urandom(16).hex()
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as target:
            if sys.platform == "darwin":
                subprocess.run(["/bin/chmod", "-N", str(directory_path / name)], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            os.fchmod(target.fileno(), 0o600)
            target.write(updated.encode("utf-8"))
            target.flush()
            os.fsync(target.fileno())
        if read_settings(directory) != original:
            fail("Settings changed during installation")
        if original[1] is None:
            os.link(name, "settings.json", src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        else:
            os.replace(name, "settings.json", src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass


def marketplace_root(marketplace: dict) -> Path:
    return Path(marketplace.get("root", marketplace.get("path", marketplace.get("installLocation", "")))).resolve()


def read_owned_install_json(path: Path, limit: int) -> object:
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size > limit:
            fail("Unsafe previous installation metadata")
        contents = file.read(limit + 1)
        if len(contents) > limit:
            fail("Oversized previous installation metadata")
        return parse_json(contents.decode("utf-8"))


def managed_codex_root(record: dict, plugin: dict, parent: Path, endpoint: str, marketplace: str) -> Path:
    previous = marketplace_root(record)
    source = plugin.get("source", {})
    origins = [item["marketplaceSource"] for item in (record, plugin) if "marketplaceSource" in item]
    marker = previous / ".umbod-install.json"
    expected = {"schema": 1, "endpoint": endpoint, "harness": "codex", "marketplace": marketplace, "sha256": previous.name}
    try:
        if (previous.parent != parent or not re.fullmatch(r"[0-9a-f]{64}", previous.name)
                or Path(record["root"]) != previous or source.get("source") != "local"
                or Path(source.get("path", "")) != previous / "plugins/umbod"
                or any(origin.get("sourceType") != "local" or Path(origin.get("source", "")) != previous for origin in origins)):
            fail("Unexpected marketplace source")
        for directory in (previous, previous / "plugins", previous / "plugins/umbod", previous / ".agents", previous / ".agents/plugins"):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                fail("Unsafe previous installation directory")
        metadata = read_owned_install_json(marker, 4096)
        if metadata != expected or type(metadata["schema"]) is not int:
            fail("Unexpected previous installation marker")
        catalog = read_owned_install_json(previous / ".agents/plugins/marketplace.json", 65536)
        entries = catalog["plugins"]
        if (catalog["name"] != marketplace or not isinstance(entries, list) or len(entries) != 1
                or entries[0]["name"] != "umbod" or entries[0]["source"] != {"source": "local", "path": "./plugins/umbod"}):
            fail("Unexpected previous marketplace catalog")
        return previous
    except (ValueError, OSError, AttributeError, KeyError, TypeError, RecursionError):
        fail("The existing Umbod plugin is not a verified install for this instance. Review your harness plugin settings manually; nothing was replaced.")


def verify_plugin(cli: str, marketplace: str, identity_key: str, destination: Path) -> dict:
    verification = [cli, "plugin", "list", "--json"]
    if cli == "codex":
        verification += ["--marketplace", marketplace]
    installed = json.loads(run(verification, "Verifying " + cli + " plugin registration"))
    installed = installed.get("installed", []) if cli == "codex" and isinstance(installed, dict) else installed
    if not isinstance(installed, list):
        fail("Unsupported installed plugin response; installation could not be verified")
    verified = [item for item in installed if item.get(identity_key) == "umbod@" + marketplace and item.get("enabled") is True and (cli == "codex" or item.get("scope") == "user")]
    if len(verified) != 1:
        fail("The intended Umbod plugin is not enabled; review your harness plugin settings")
    plugin_source = verified[0].get("source", {}).get("path") if cli == "codex" else verified[0].get("readFromFolder")
    if not isinstance(plugin_source, str) or Path(plugin_source).resolve() != destination / "plugins/umbod":
        fail("The installed Umbod plugin source could not be verified; review your harness plugin settings")
    return verified[0]


def codex_marketplace_roots(marketplace: str) -> list:
    response = json.loads(run(["codex", "plugin", "marketplace", "list", "--json"], "Inspecting the Umbod marketplace registration"))
    roots = []
    for item in response["marketplaces"]:
        if item.get("name") != marketplace:
            continue
        root = marketplace_root(item)
        origin = item.get("marketplaceSource", {"sourceType": "local", "source": str(root)})
        if Path(item["root"]) != root or origin.get("sourceType") != "local" or Path(origin.get("source", "")) != root:
            fail("The Codex marketplace is not registered from the expected local directory")
        roots.append(root)
    return roots


def upgrade_codex(record: dict, plugin: dict, destination: Path, endpoint: str, marketplace: str, version: str) -> None:
    previous = managed_codex_root(record, plugin, destination.parent, endpoint, marketplace)
    remove = ["codex", "plugin", "marketplace", "remove"]
    register = ["codex", "plugin", "marketplace", "add"]
    install = ["codex", "plugin", "add", "umbod@" + marketplace]
    run(remove + ["--help"], "Checking Codex marketplace upgrade support")
    if codex_marketplace_roots(marketplace) != [previous]:
        fail("The Umbod marketplace changed during installation; nothing was replaced. Retry the installer.")
    previous_version = verify_plugin("codex", marketplace, "pluginId", previous).get("version")
    if not isinstance(previous_version, str) or not previous_version:
        fail("The previous Codex plugin version could not be verified")
    try:
        run(remove + [marketplace], "Switching the Umbod marketplace to the new package", capture=False)
        run(register + [str(destination)], "Registering the new Umbod package", capture=False)
        run(install, "Upgrading the Umbod plugin", capture=False)
        if codex_marketplace_roots(marketplace) != [destination]:
            fail("The upgraded Codex marketplace root could not be verified")
        if verify_plugin("codex", marketplace, "pluginId", destination).get("version") != version:
            fail("The upgraded Codex plugin version could not be verified")
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError, TypeError, AttributeError, IndexError):
        try:
            managed_codex_root(record, plugin, destination.parent, endpoint, marketplace)
            roots = codex_marketplace_roots(marketplace)
            if len(roots) > 1 or (roots and roots[0] not in {previous, destination}):
                fail("Marketplace changed during upgrade")
            if roots == [destination]:
                run(remove + [marketplace], "Removing the failed Umbod marketplace registration", capture=False)
                roots = []
            if not roots:
                run(register + [str(previous)], "Restoring the previous Umbod marketplace", capture=False)
            run(install, "Restoring the previous Umbod plugin", capture=False)
            if codex_marketplace_roots(marketplace) != [previous]:
                fail("The previous Codex marketplace root could not be verified")
            if verify_plugin("codex", marketplace, "pluginId", previous).get("version") != previous_version:
                fail("The previous Codex plugin version could not be verified")
        except (ValueError, OSError, subprocess.CalledProcessError, KeyError, TypeError, AttributeError, IndexError):
            fail("Umbod upgrade failed and the previous registration could not be restored automatically. The old package was kept; review your Codex marketplace settings before retrying.")
        fail("Umbod upgrade failed. The previous Codex plugin was restored; retry the installer after reviewing the error above.")


def main() -> None:
    if sys.version_info < (3, 8):
        fail("Python 3.8 or newer is required")
    parser = argparse.ArgumentParser(description="Install the Umbod plugin without changing standalone MCP connections")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--harness", choices=["codex", "claude-code"], required=True)
    parser.add_argument("--expected-endpoint", required=True)
    parser.add_argument("--logs-endpoint", default="")
    parser.add_argument("--platform", choices=["macos", "linux"])
    args = parser.parse_args()
    telemetry = telemetry_settings(args.harness)
    claim = installation_claim()
    if claim and telemetry:
        fail("Only one telemetry setup method can be used at a time")
    if claim and not args.logs_endpoint:
        fail("Telemetry setup is unavailable. Copy a fresh install command from Umbod.")
    if telemetry:
        apply_claude_settings(telemetry, write=False)
    detected = {"Darwin": "macos", "Linux": "linux"}.get(platform.system())
    if detected is None or args.platform not in {None, detected}:
        fail("Unsupported platform. Use install.ps1 on native Windows; use linux inside WSL.")
    expected_endpoint = validate_url(args.expected_endpoint)
    if not expected_endpoint.endswith("/mcp"):
        fail("Expected endpoint must be a normalized MCP URL")
    base = validate_url(args.base_url.rstrip("/"))
    if not urlsplit(base).path.endswith("/install/v1"):
        fail("Base URL must end with /install/v1")
    cli = "codex" if args.harness == "codex" else "claude"
    command_timeout()
    print("Checking " + args.harness + " installer prerequisites...", flush=True)
    checksum_tool = "shasum" if detected == "macos" else "sha256sum"
    for executable in ["curl", checksum_tool, cli]:
        if shutil.which(executable) is None:
            fail("Required command is missing: " + executable)
    action = "add" if cli == "codex" else "install"
    for arguments in [[cli, "plugin", "marketplace", "add", "--help"], [cli, "plugin", action, "--help"], [cli, "plugin", "marketplace", "list", "--help"]]:
        run(arguments, "Checking " + cli + " plugin command support")
    expected_marketplace = "umbod-" + hashlib.sha256(expected_endpoint.encode()).hexdigest()[:12]
    marketplaces = json.loads(run([cli, "plugin", "marketplace", "list", "--json"], "Inspecting " + cli + " configured marketplaces"))
    if cli == "codex" and isinstance(marketplaces, dict):
        marketplaces = marketplaces.get("marketplaces")
    if not isinstance(marketplaces, list):
        fail("Unsupported marketplace list response; update your harness")
    if cli == "codex":
        names = {expected_marketplace}
        for item in marketplaces:
            name = item.get("name")
            if not isinstance(name, str) or not name:
                fail("Unsupported marketplace name; update your harness")
            if name == "openai-curated-remote":
                fail("A configured marketplace uses the reserved Codex remote catalog name. Review your local marketplaces manually; nothing was changed.")
            names.add(name)
        initial_plugins = []
        for name in sorted(names):
            response = json.loads(run([cli, "plugin", "list", "--json", "--marketplace", name], "Inspecting " + cli + " local plugins"))
            installed = response.get("installed") if isinstance(response, dict) else None
            if not isinstance(installed, list):
                fail("Unsupported installed plugin response; update your harness")
            initial_plugins.extend(installed)
    else:
        initial_plugins = json.loads(run([cli, "plugin", "list", "--json"], "Inspecting " + cli + " installed plugins"))
        if not isinstance(initial_plugins, list):
            fail("Unsupported installed plugin response; update your harness")
    identity_key = "pluginId" if cli == "codex" else "id"
    for item in initial_plugins:
        identity = item.get(identity_key, "")
        if identity.startswith("umbod@") and identity != "umbod@" + expected_marketplace and item.get("enabled") is True:
            fail("An active Umbod plugin for another instance exists. Review your harness plugin list and resolve it manually; nothing was replaced.")
        if identity == "umbod@" + expected_marketplace and item.get("enabled") is not True:
            fail("The Umbod plugin is already installed but disabled. Review your harness plugin settings manually.")
    if cli == "codex":
        servers = json.loads(run([cli, "mcp", "list", "--json", "--disable", "plugins"], "Inspecting " + cli + " standalone MCP connections"))
        if not isinstance(servers, list):
            fail("Unsupported Codex MCP list response")
        conflict = any(server.get("name", "").lower() == "umbod" for server in servers)
    else:
        result = execute([cli, "mcp", "get", "umbod"], "Inspecting " + cli + " standalone MCP connections", command_timeout())
        conflict = result.returncode == 0
        if not conflict and 'No MCP server named "umbod"' not in result.stdout + result.stderr:
            fail("Could not safely inspect standalone MCP connections; run claude mcp get umbod")
    if conflict:
        fail("A standalone umbod MCP connection already exists. Review it with " + cli + " mcp get umbod and resolve it manually before retrying; nothing was removed.")
    print("Downloading and verifying Umbod plugin...", flush=True)
    with tempfile.TemporaryDirectory(prefix="umbod-install-") as temporary:
        work = Path(temporary)
        for name in ["package.zip", "package.sha256", "marketplace.txt", "endpoint.txt"]:
            fetch(base + "/" + args.harness + "/" + name, work / name)
        digest = read_line(work / "package.sha256", "[0-9a-f]{64}")
        marketplace = read_line(work / "marketplace.txt", "umbod-[0-9a-f]{12}")
        endpoint = validate_url(read_line(work / "endpoint.txt", "[^\\r\\n]+"))
        if endpoint != expected_endpoint:
            fail("Downloaded endpoint does not match --expected-endpoint; no configuration was changed")
        if marketplace != "umbod-" + hashlib.sha256(endpoint.encode()).hexdigest()[:12]:
            fail("Marketplace does not match endpoint identity")
        checksum_args = [checksum_tool] + (["-a", "256"] if detected == "macos" else [])
        actual = run(checksum_args + [str(work / "package.zip")], "Verifying package checksum").split()[0]
        if actual != digest:
            fail("Package SHA256 mismatch; no configuration was changed")
        catalog = ".agents/plugins/marketplace.json" if cli == "codex" else ".claude-plugin/marketplace.json"
        manifest = "plugins/umbod/" + (".codex-plugin" if cli == "codex" else ".claude-plugin") + "/plugin.json"
        allowed = {catalog, manifest, "plugins/umbod/.mcp.json", "plugins/umbod/skills/run-diagnostics/SKILL.md", "plugins/umbod/LICENSE"}
        stage = work / "staging"
        stage.mkdir(mode=0o700)
        with zipfile.ZipFile(work / "package.zip") as archive:
            entries = archive.infolist()
            if len(entries) != len(allowed) or {entry.filename for entry in entries} != allowed:
                fail("Package contains unexpected, duplicate, or unsafe ZIP entries")
            if any(stat.S_IFMT(entry.external_attr >> 16) not in {0, stat.S_IFREG} or entry.file_size > 2097152 for entry in entries):
                fail("Package contains symlinks, special files, or oversized entries")
            contents = {entry.filename: archive.read(entry) for entry in entries}
            market_data = json.loads(contents[catalog])
            if market_data.get("name") != marketplace:
                fail("Package marketplace identity mismatch")
            if set(market_data) - {"name", "plugins", "interface", "owner"}:
                fail("Package marketplace contains unsupported configuration")
            plugins = market_data.get("plugins", [])
            source = {"source": "local", "path": "./plugins/umbod"} if cli == "codex" else "./plugins/umbod"
            if len(plugins) != 1 or plugins[0].get("name") != "umbod" or plugins[0].get("source") != source:
                fail("Package marketplace source is unsafe")
            if set(plugins[0]) - {"name", "source", "policy", "category"}:
                fail("Package marketplace plugin contains unsupported configuration")
            manifest_data = json.loads(contents[manifest])
            if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", manifest_data.get("version", "")):
                fail("Package plugin version is unsafe")
            manifest_keys = {"name", "version", "description", "author", "homepage", "repository", "license", "skills", "mcpServers"}
            if set(manifest_data) - manifest_keys or manifest_data.get("name") != "umbod" or manifest_data.get("skills") != "./skills/" or manifest_data.get("mcpServers") != "./.mcp.json":
                fail("Package plugin manifest is unsafe")
            if json.loads(contents["plugins/umbod/.mcp.json"]) != {"mcpServers": {"umbod": {"type": "http", "url": endpoint}}}:
                fail("Package MCP endpoint mismatch")
            for name, content in contents.items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        marker_name = ".umbod-install.json"
        marker = json.dumps({"schema": 1, "endpoint": endpoint, "harness": args.harness, "marketplace": marketplace, "sha256": digest}, sort_keys=True).encode()
        (stage / marker_name).write_bytes(marker)
        allowed.add(marker_name)
        contents[marker_name] = marker
        if Path.home().is_symlink():
            fail("Refusing a symbolic-link home directory")
        home = Path.home().resolve()
        data_home = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share"))) if detected == "linux" else home / "Library/Application Support"
        if not data_home.is_absolute():
            fail("XDG_DATA_HOME must be an absolute path")
        root = data_home / ("Umbod/plugins" if detected == "macos" else "umbod/plugins")
        parent = root / marketplace / args.harness
        boundary = home if home == data_home or home in data_home.parents else data_home
        ensure_owned_directory(parent, boundary)
        lock = parent / ".install.lock"
        try:
            lock.mkdir(mode=0o700)
        except FileExistsError:
            fail("Another installation is running or a stale lock exists: " + str(lock) + ". Retry after it finishes; review stale locks manually.")
        atexit.register(lock.rmdir)
        destination = parent / digest
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir():
                fail("Existing content-addressed installation is unsafe")
            existing = {str(path.relative_to(destination)): path for path in destination.rglob("*") if not path.is_dir() or path.is_symlink()}
            if set(existing) != allowed or any(path.is_symlink() or path.read_bytes() != contents[name] for name, path in existing.items()):
                fail("Existing content-addressed installation was modified; review it manually")
        else:
            staged = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
            try:
                shutil.copytree(stage, staged, dirs_exist_ok=True)
                os.rename(staged, destination)
            finally:
                if staged.exists():
                    shutil.rmtree(staged)
        existing_plugins = [item for item in initial_plugins if item.get(identity_key) == "umbod@" + marketplace]
        if len(existing_plugins) > 1:
            fail("Multiple Umbod plugin registrations exist; review your harness plugin settings manually")
        matches = [item for item in marketplaces if item.get("name") == marketplace]
        if cli == "codex" and existing_plugins and len(matches) == 1 and marketplace_root(matches[0]) != destination:
            upgrade_codex(matches[0], existing_plugins[0], destination, endpoint, marketplace, manifest_data["version"])
        else:
            if existing_plugins:
                existing_source = existing_plugins[0].get("source", {}).get("path") if cli == "codex" else existing_plugins[0].get("readFromFolder")
                if not isinstance(existing_source, str) or Path(existing_source).resolve() != destination / "plugins/umbod" or (cli == "claude" and existing_plugins[0].get("scope") != "user"):
                    fail("The existing Umbod plugin uses another source or scope. Review your harness plugin settings manually; nothing was replaced.")
            if matches:
                if len(matches) != 1 or marketplace_root(matches[0]) != destination:
                    fail("Marketplace already exists at another path. Review it manually; nothing was replaced.")
            else:
                run([cli, "plugin", "marketplace", "add", str(destination)], "Registering " + cli + " local marketplace", capture=False)
            if existing_plugins:
                print("Umbod plugin already installed; verifying registration...", flush=True)
            else:
                command = [cli, "plugin", action, "umbod@" + marketplace]
                if cli == "claude":
                    command += ["--scope", "user"]
                run(command, "Installing " + cli + " Umbod plugin", capture=False)
            verified = verify_plugin(cli, marketplace, identity_key, destination)
            if cli == "codex" and verified.get("version") != manifest_data["version"]:
                fail("The Codex plugin version does not match the verified Umbod package. Review your Codex plugin settings before retrying.")
    lock.rmdir()
    atexit.unregister(lock.rmdir)
    if claim and cli == "codex":
        install_codex_telemetry(validate_logs_endpoint(args.logs_endpoint),
                                lambda: redeem_claim(base, args.harness, claim, args.logs_endpoint))
    elif claim:
        placeholder = "umbod_pat_v1_" + "0" * 32 + "_" + "A" * 43
        apply_claude_settings(
            claude_settings(args.logs_endpoint, placeholder), write=True,
            redeem=lambda: claude_settings(*redeem_claim(base, args.harness, claim, args.logs_endpoint)),
        )
        print("Claude Code logs-only telemetry settings applied. Delivery has not been verified.", flush=True)
    elif telemetry:
        apply_claude_settings(telemetry, write=True)
        print("Claude Code logs-only telemetry settings applied. Delivery has not been verified.", flush=True)
    harness_name = "Codex" if args.harness == "codex" else "Claude Code"
    print("\n"
          "      |\n"
          "      |\n"
          "     /|\\\n"
          "    / | \\\n"
          "   |  |  |\n"
          "   |     |\n"
          "\n"
          "   Umbod\n"
          "\n"
          f"Umbod plugin installed for {harness_name}. Plugin registration verified.\n"
          "\n"
          f"1. {'Start Codex when you are ready.' if cli == 'codex' else 'Restart Claude Code.'}\n"
          "2. Open /mcp and sign in if prompted.\n"
          "3. Ask your agent to discover available Umbod connected apps.\n"
          "\n"
          "Connection has not been verified. Installation does not verify access to connected apps.\n", flush=True)


try:
    main()
except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile, KeyError, TypeError, AttributeError, IndexError) as error:
    sys.exit("Umbod installation stopped: " + str(error))
PY
)
umbod_install "$@"
