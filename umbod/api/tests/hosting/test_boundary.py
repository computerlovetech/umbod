import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

import umbod.hosting as hosting

ROOT = Path(__file__).resolve().parents[4]


def test_public_exports_and_explicit_keyword_only_signatures() -> None:
    expected_exports = {
        "AccessToken", "AppConfig", "ConnectorRegistration",
        "InMemoryGroupConnectorToolPermissions", "JwtClaims", "JwtVerificationError",
        "JwtVerifier", "MCPAuthProvider", "McpToolInvocationLogEvent",
        "McpToolInvocationLogSink", "OAuthService", "TokenVerifier",
        "create_mcp_app", "create_rest_app",
    }
    assert set(hosting.__all__) == expected_exports
    for name in expected_exports:
        assert getattr(hosting, name) is not None
    assert not hasattr(hosting, "PublicAppConfig")
    assert not hasattr(hosting, "PublicAppRuntimeContext")
    for factory, expected_names in (
        (hosting.create_rest_app, ("settings", "connector_registrations", "admin_verifier", "oauth_service", "user_authentication")),
        (hosting.create_mcp_app, ("settings", "auth_provider", "group_permission_runtime_state", "invocation_log_sink")),
    ):
        parameters = list(inspect.signature(factory).parameters.values())
        assert tuple(parameter.name for parameter in parameters) == expected_names
        assert parameters[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert parameters[0].default is inspect.Parameter.empty
        for parameter in parameters[1:]:
            expected_kind = (
                inspect.Parameter.VAR_KEYWORD
                if parameter.name == "user_authentication" else inspect.Parameter.KEYWORD_ONLY
            )
            assert parameter.kind == expected_kind
            assert parameter.default is inspect.Parameter.empty


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


@pytest.mark.parametrize("path", sorted((ROOT / "desktop/python/umbod_desktop").rglob("*.py")))
def test_desktop_uses_only_supported_hosting_imports(path: Path) -> None:
    package = ROOT / "desktop/python/umbod_desktop"
    parts = path.relative_to(package).with_suffix("").parts
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


def test_checker_resolves_nested_relative_imports() -> None:
    assert imports("def factory():\n from ..contracts import ConnectorDefinition", "umbod_desktop.backend_integration.administration", False) == [
        ("umbod_desktop.contracts", ("ConnectorDefinition",))
    ]
    assert violations("from ..contracts import ConnectorDefinition", "umbod_desktop.backend_integration.administration") == []
    assert violations("from umbod.hosting import AppConfig", "umbod_desktop.backend_integration.configuration") == []


def test_import_does_not_read_environment_or_create_applications(tmp_path: Path) -> None:
    program = (
        "import os; before = dict(os.environ); "
        "import umbod.config as config; "
        "config.load_app_config = config.load_server_app_config = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('config loaded')); "
        "import umbod.hosting; import sys; "
        "assert dict(os.environ) == before; "
        "assert 'umbod.hosting.mcp_service' not in sys.modules; "
        "assert 'umbod.hosting.rest_service' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", program], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
