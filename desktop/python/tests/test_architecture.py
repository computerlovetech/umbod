import ast
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "umbod_desktop"
CORE = {
    "contracts", "ports", "usage", "backward_compatibility.contracts",
    "backward_compatibility.ports", "backward_compatibility.migration",
    "backward_compatibility.tool_names",
}
HOSTING = {
    "AccessToken", "AppConfig", "ConnectorRegistration",
    "InMemoryGroupConnectorToolPermissions", "JwtClaims", "JwtVerificationError",
    "JwtVerifier", "MCPAuthProvider", "McpToolInvocationLogEvent",
    "McpToolInvocationLogSink", "OAuthService", "TokenVerifier",
    "create_mcp_app", "create_rest_app",
}
RESIDUAL = {
    "umbod_desktop.backward_compatibility.adapters.oauth": {
        "umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth": {"AuthorizationDocument"},
    },
    "umbod_desktop.backend_integration.configuration": {
        "umbod.config.secret_derivation": {"derive_secret"},
    },
    "umbod_desktop.backend_integration.naming": {
        "umbod.core.capabilities.tools.names": {"mangle_public_tool_name"},
        "umbod.core.connectors.downstream_mcp.models": {"default_tool_name_prefix"},
    },
    "umbod_desktop.backend_integration.models": {
        "umbod.core.connectors.downstream_mcp.models": {"EndpointUrl"},
    },
    "umbod_desktop.backend_integration.oauth": {
        "umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth": {
            "AuthorizationDocument", "ConnectorOAuthStorage", "SignInRequired",
        },
        "umbod.core.connectors.downstream_mcp.oauth.ports": {"OAuthConnection"},
    },
    "umbod_desktop.backend_integration.transports": {
        "umbod.core.connectors.downstream_mcp.oauth.provider": {
            "RuntimeOAuth", "response_authentication_status",
        },
    },
}


def imports(source: str, module: str, is_package: bool) -> list[tuple[str, tuple[str, ...]]]:
    found = []
    package = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend((alias.name, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                prefix = package[:len(package) - node.level + 1]
                base = ".".join((*prefix, *base.split("."))).rstrip(".")
            found.append((base, tuple(alias.name for alias in node.names)))
    return found


def violations(source: str, module: str, is_package: bool = False) -> list[str]:
    failures = []
    adapter = module.startswith("umbod_desktop.backend_integration")
    runtime = module == "umbod_desktop.runtime"
    core = module.removeprefix("umbod_desktop.") in CORE
    for target, names in imports(source, module, is_package):
        candidates = (target, *(f"{target}.{name}" for name in names))
        if not module.startswith("umbod_desktop.backward_compatibility") and module not in {
            "umbod_desktop.main", "umbod_desktop.runtime",
        } and any(candidate == "umbod_desktop.backward_compatibility" or candidate.startswith("umbod_desktop.backward_compatibility.") for candidate in candidates):
            failures.append(target)
        if target == "umbod" or target.startswith("umbod."):
            permitted = (adapter or runtime) and target == "umbod.hosting" and bool(names) and set(names) <= HOSTING
            permitted = permitted or (bool(names) and target in RESIDUAL.get(module, {}) and set(names) <= RESIDUAL[module][target])
            if not permitted:
                failures.append(target)
        if not adapter and not runtime and any(
            candidate == "umbod_desktop.backend_integration" or candidate.startswith("umbod_desktop.backend_integration.")
            for candidate in candidates
        ):
            failures.append(target)
        if core and any(candidate in {
            "umbod_desktop.runtime", "umbod_desktop.storage", "umbod_desktop.security",
        } for candidate in candidates):
            failures.append(target)
        if core and target.split(".")[0] in {"httpx", "httpx2", "fastapi", "starlette", "keyring"}:
            failures.append(target)
        if not adapter and module not in {"umbod_desktop.backward_compatibility.adapters.legacy_host", "umbod_desktop.backward_compatibility.adapters.administration"} and target.split(".")[0] == "httpx":
            failures.append(target)
    if module not in {"umbod_desktop.backend_integration.administration", "umbod_desktop.backward_compatibility.adapters.administration"} and any(
        isinstance(node, ast.Constant) and isinstance(node.value, str) and "/api/admin" in node.value
        for node in ast.walk(ast.parse(source))
    ):
        failures.append("administration HTTP path")
    return failures


def transitive_violations(sources: dict[str, tuple[str, bool]], root: str) -> list[str]:
    pending = [root]
    visited: set[str] = set()
    failures = []
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        source, is_package = sources[module]
        for target, names in imports(source, module, is_package):
            candidates = (target, *(f"{target}.{name}" for name in names))
            for candidate in candidates:
                if candidate in sources:
                    pending.append(candidate)
            if target.split(".")[0] in {"umbod", "httpx", "httpx2", "fastapi", "starlette", "keyring"}:
                failures.append(target)
            if any(candidate in {
                "umbod_desktop.runtime", "umbod_desktop.storage", "umbod_desktop.security",
            } or candidate.startswith("umbod_desktop.backend_integration") for candidate in candidates):
                failures.append(target)
    return failures


@pytest.mark.parametrize("path", sorted(PACKAGE.rglob("*.py")))
def test_desktop_dependency_direction(path: Path) -> None:
    relative = path.relative_to(PACKAGE).with_suffix("")
    parts = relative.parts
    is_package = parts[-1] == "__init__"
    module = ".".join(("umbod_desktop", *(parts[:-1] if is_package else parts)))
    assert violations(path.read_text(), module, is_package) == []


@pytest.mark.parametrize("source,module,is_package", [
    ("def run():\n import umbod.rest.dependencies", "umbod_desktop.runtime", False),
    ("from umbod.hosting.contracts import AppConfig", "umbod_desktop.backend_integration.configuration", False),
    ("from umbod.core.connectors.downstream_mcp.models import Connector", "umbod_desktop.backend_integration.models", False),
    ("from umbod.core.connectors.downstream_mcp.models import EndpointUrl", "umbod_desktop.backend_integration.naming", False),
    ("from umbod.core.connectors.downstream_mcp.oauth.provider import RuntimeOAuth", "umbod_desktop.backend_integration.usage", False),
    ("import umbod.core.capabilities.tools.names", "umbod_desktop.backend_integration.naming", False),
    ("from ..backend_integration.naming import BackendToolNamingPolicy", "umbod_desktop.backward_compatibility.migration", False),
    ("from .backward_compatibility import migration", "umbod_desktop.endpoint", False),
    ("from ..backward_compatibility.authentication import LegacyAgentCredentials", "umbod_desktop.backend_integration.authentication", False),
    ("from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import ConnectorOAuthStorage", "umbod_desktop.backward_compatibility.adapters.oauth", False),
    ("import httpx", "umbod_desktop.backward_compatibility.profile", False),
    ("from .. import backend_integration", "umbod_desktop.backward_compatibility.tool_names", False),
    ("from umbod_desktop import backend_integration", "umbod_desktop.usage", False),
    ("from ..runtime import create_desktop_app", "umbod_desktop.backward_compatibility.migration", False),
    ("from . import runtime", "umbod_desktop.ports", False),
    ("from .storage import DesktopState", "umbod_desktop.usage", False),
    ("from .security import CredentialVault", "umbod_desktop.ports", False),
    ("from starlette.types import ASGIApp", "umbod_desktop.contracts", False),
    ("import httpx", "umbod_desktop.backward_compatibility.migration", False),
    ('path = "/api/admin/connectors/mcp"', "umbod_desktop.legacy", False),
    ("from ..backend_integration import naming", "umbod_desktop.nested", True),
])
def test_checker_rejects_forbidden_synthetic_imports(source: str, module: str, is_package: bool) -> None:
    assert violations(source, module, is_package)


@pytest.mark.parametrize("root", sorted(CORE))
def test_use_case_transitive_dependencies_are_desktop_owned(root: str) -> None:
    sources = {}
    for path in PACKAGE.rglob("*.py"):
        parts = path.relative_to(PACKAGE).with_suffix("").parts
        is_package = parts[-1] == "__init__"
        module = ".".join(("umbod_desktop", *(parts[:-1] if is_package else parts)))
        sources[module] = (path.read_text(), is_package)
    assert transitive_violations(sources, f"umbod_desktop.{root}") == []


def test_transitive_checker_follows_relative_helper_imports() -> None:
    sources = {
        "umbod_desktop.migration": ("from .helpers import prepare", False),
        "umbod_desktop.helpers": ("def prepare():\n from starlette.types import ASGIApp", False),
    }
    assert transitive_violations(sources, "umbod_desktop.migration") == ["starlette.types"]


def test_fresh_core_imports_do_not_load_backend_or_outer_adapters(tmp_path: Path) -> None:
    program = '''
import importlib.abc
import sys

class BoundaryGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:
        root = fullname.split(".")[0]
        if root in {"umbod", "httpx", "httpx2", "fastapi", "starlette", "keyring"} or fullname.startswith("umbod_desktop.backend_integration") or fullname in {"umbod_desktop.runtime", "umbod_desktop.security", "umbod_desktop.storage"}:
            raise AssertionError("Unexpected core dependency: " + fullname)

sys.meta_path.insert(0, BoundaryGuard())
from umbod_desktop import contracts, ports, usage
from umbod_desktop.backward_compatibility import contracts as legacy_contracts, ports as legacy_ports, migration, tool_names
assert all(module is not None for module in (contracts, ports, usage, legacy_contracts, legacy_ports, migration, tool_names))
assert not any(name == "umbod" or name.startswith("umbod.") for name in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", program], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_checker_resolves_nested_relative_imports() -> None:
    assert imports("def factory():\n from ..contracts import ConnectorDefinition", "umbod_desktop.backend_integration.administration", False) == [
        ("umbod_desktop.contracts", ("ConnectorDefinition",))
    ]
    assert violations("from ..contracts import ConnectorDefinition", "umbod_desktop.backend_integration.administration") == []
    assert violations("from umbod.hosting import AppConfig", "umbod_desktop.backend_integration.configuration") == []
