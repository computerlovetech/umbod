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
    python3 - "$@" <<'PY'
import argparse
import atexit
import base64
import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


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
        endpoint, token = payload["endpoint"], payload["token"]
        if not isinstance(token, str) or not re.fullmatch(r"umbod_pat_v1_[0-9a-f]{32}_[A-Za-z0-9_-]{43}", token):
            fail("Invalid token")
        if not isinstance(endpoint, str) or len(endpoint) > 2048 or not re.fullmatch(r"[A-Za-z0-9:/._~!&'()*+,;=@%\[\]-]+", endpoint):
            fail("Invalid endpoint")
        if re.search(r"%(?:[01][0-9a-f]|7f)|%(?![0-9a-f]{2})", endpoint, re.IGNORECASE):
            fail("Invalid URI encoding")
        parsed = urlsplit(validate_url(endpoint))
        if not re.fullmatch(r"(?:\[[A-Fa-f0-9:.]+\]|[A-Za-z0-9.-]+)(?::[0-9]+)?", parsed.netloc) or not parsed.path.endswith("/v1/logs"):
            fail("Invalid logs URL")
    except (ValueError, OverflowError, RecursionError):
        fail("Invalid Claude Code telemetry payload")
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


def open_configuration_directory(home: Path, create: bool) -> int:
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


def apply_claude_settings(desired: dict, write: bool) -> None:
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
                updated = merge_settings(original[0].decode("utf-8"), desired)
                save_settings(home / ".claude", directory, original, updated)
            finally:
                os.rmdir(lock, dir_fd=directory)
        finally:
            os.close(directory)
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


def main() -> None:
    if sys.version_info < (3, 8):
        fail("Python 3.8 or newer is required")
    parser = argparse.ArgumentParser(description="Install the Umbod plugin without changing standalone MCP connections")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--harness", choices=["codex", "claude-code"], required=True)
    parser.add_argument("--expected-endpoint", required=True)
    parser.add_argument("--platform", choices=["macos", "linux"])
    args = parser.parse_args()
    telemetry = telemetry_settings(args.harness)
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
        allowed = {catalog, manifest, "plugins/umbod/.mcp.json", "plugins/umbod/skills/umbod-connected-apps/SKILL.md", "plugins/umbod/skills/umbod-agent-behaviour/SKILL.md", "plugins/umbod/skills/run-diagnostics/SKILL.md", "plugins/umbod/LICENSE"}
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
        if existing_plugins:
            existing_source = existing_plugins[0].get("source", {}).get("path") if cli == "codex" else existing_plugins[0].get("readFromFolder")
            if not isinstance(existing_source, str) or Path(existing_source).resolve() != destination / "plugins/umbod" or (cli == "claude" and existing_plugins[0].get("scope") != "user"):
                fail("The existing Umbod plugin uses another source or scope. Review your harness plugin settings manually; nothing was replaced.")
        matches = [item for item in marketplaces if item.get("name") == marketplace]
        if matches:
            registered_path = matches[0].get("root", matches[0].get("path", matches[0].get("installLocation", "")))
            if len(matches) != 1 or Path(registered_path).resolve() != destination:
                fail("Marketplace already exists at another path. Review it manually; nothing was replaced.")
        else:
            run([cli, "plugin", "marketplace", "add", str(destination)], "Registering " + cli + " local marketplace", capture=False)
        command = [cli, "plugin", action, "umbod@" + marketplace]
        if cli == "claude":
            command += ["--scope", "user"]
        if existing_plugins:
            print("Umbod plugin already installed; verifying registration...", flush=True)
        else:
            run(command, "Installing " + cli + " Umbod plugin", capture=False)
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
    if telemetry:
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
          f"1. Restart {harness_name}.\n"
          "2. Open /mcp and sign in if prompted.\n"
          "3. Ask your agent to discover available Umbod connected apps.\n"
          "\n"
          "Connection has not been verified. Installation does not verify access to connected apps.\n")


try:
    main()
except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile, KeyError, TypeError, AttributeError, IndexError) as error:
    sys.exit("Umbod installation stopped: " + str(error))
PY
)
umbod_install "$@"
