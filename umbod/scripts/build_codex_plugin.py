from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import shlex
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PLUGIN_VERSION = "0.1.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPOSITORY_ROOT / "skills/integrations/umbod-connected-apps/SKILL.md"


def normalize_endpoint(value: str) -> str:
    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("The MCP endpoint must be an absolute URL without whitespace")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        parsed.port
    except ValueError as error:
        raise ValueError("The MCP endpoint has an invalid host or port") from error
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("The MCP endpoint must use HTTP or HTTPS with a host")
    if parsed.username is not None or parsed.password is not None or "?" in value or "#" in value:
        raise ValueError("The MCP endpoint must not contain credentials, a query, or a fragment")
    if any(character in value for character in ('\\', '$', '{', '}')):
        raise ValueError("The MCP endpoint must be a literal URL without placeholders or backslashes")
    if parsed.scheme == "http" and not is_loopback(host):
        raise ValueError("Non-loopback MCP endpoints must use HTTPS")
    path = parsed.path.rstrip("/")
    if not path.endswith("/mcp"):
        path += "/mcp"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def marketplace_name(endpoint: str) -> str:
    identity = hashlib.sha256(normalize_endpoint(endpoint).encode("utf-8")).hexdigest()[:12]
    return f"umbod-{identity}"


def render_package(endpoint: str, skill: str, license_text: str) -> Mapping[str, str]:
    selected_endpoint = normalize_endpoint(endpoint)
    if not skill.strip() or not license_text.strip():
        raise ValueError("The canonical skill and license must not be empty")
    marketplace = {
        "name": marketplace_name(selected_endpoint),
        "interface": {"displayName": "Umbod"},
        "plugins": [
            {
                "name": "umbod",
                "source": {"source": "local", "path": "./plugins/umbod"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
                "category": "Productivity",
            }
        ],
    }
    manifest = {
        "name": "umbod",
        "version": PLUGIN_VERSION,
        "description": "Discover and use the connected apps available to your Umbod account.",
        "author": {"name": "Computerlove", "url": "https://computerlove.tech"},
        "homepage": "https://umbod.ai",
        "repository": "https://github.com/computerlovetech/umbod",
        "license": "MIT",
        "skills": "./skills/",
        "mcpServers": "./.mcp.json",
    }
    mcp = {"mcpServers": {"umbod": {"type": "http", "url": selected_endpoint}}}
    return {
        ".agents/plugins/marketplace.json": json.dumps(marketplace, indent=2) + "\n",
        "plugins/umbod/.codex-plugin/plugin.json": json.dumps(manifest, indent=2) + "\n",
        "plugins/umbod/.mcp.json": json.dumps(mcp, indent=2) + "\n",
        "plugins/umbod/skills/umbod-connected-apps/SKILL.md": skill,
        "plugins/umbod/LICENSE": license_text,
    }


def write_package(destination: Path, files: Mapping[str, str]) -> None:
    for name in files:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Package entries must stay inside the destination")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    except OSError:
        shutil.rmtree(destination)
        raise


def build_package(endpoint: str, destination: Path) -> str:
    files = render_package(
        endpoint,
        SKILL_PATH.read_text(encoding="utf-8"),
        (REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8"),
    )
    write_package(destination, files)
    return marketplace_name(endpoint)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an endpoint-specific Umbod marketplace for Codex CLI")
    parser.add_argument("--endpoint", required=True, help="Umbod MCP URL or deployment origin")
    parser.add_argument("--output", required=True, type=Path, help="New marketplace directory; existing paths are never replaced")
    options = parser.parse_args(arguments)
    destination = options.output.expanduser().resolve()
    try:
        name = build_package(options.endpoint, destination)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Could not build the Codex plugin: {error}\n")
    print(f"codex plugin marketplace add {shlex.quote(str(destination))}")
    print(f"codex plugin add umbod@{name}")
    print("Start a new Codex session and inspect /mcp. If sign-in is required, run: codex mcp login umbod")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
