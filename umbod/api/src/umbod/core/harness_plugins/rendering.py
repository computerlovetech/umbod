import hashlib
import ipaddress
import json
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

Harness = Literal["codex", "claude-code"]
PLUGIN_VERSION = "0.1.0"


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


def render_package(
    endpoint: str, skill: str, license_text: str, harness: Harness, behaviour_skill: str,
) -> Mapping[str, str]:
    if harness not in {"codex", "claude-code"}:
        raise ValueError("Unsupported harness")
    selected_endpoint = normalize_endpoint(endpoint)
    if not skill.strip() or not license_text.strip() or not behaviour_skill.strip():
        raise ValueError("The canonical skills and license must not be empty")
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
    marketplace_path = ".agents/plugins/marketplace.json"
    manifest_path = "plugins/umbod/.codex-plugin/plugin.json"
    if harness == "claude-code":
        marketplace = {
            "name": marketplace_name(selected_endpoint),
            "owner": {"name": "Computerlove", "url": "https://computerlove.tech"},
            "plugins": [{"name": "umbod", "source": "./plugins/umbod"}],
        }
        marketplace_path = ".claude-plugin/marketplace.json"
        manifest_path = "plugins/umbod/.claude-plugin/plugin.json"
    mcp = {"mcpServers": {"umbod": {"type": "http", "url": selected_endpoint}}}
    return {
        marketplace_path: json.dumps(marketplace, indent=2) + "\n",
        manifest_path: json.dumps(manifest, indent=2) + "\n",
        "plugins/umbod/.mcp.json": json.dumps(mcp, indent=2) + "\n",
        "plugins/umbod/skills/umbod-connected-apps/SKILL.md": skill,
        "plugins/umbod/skills/umbod-agent-behaviour/SKILL.md": behaviour_skill,
        "plugins/umbod/LICENSE": license_text,
    }

