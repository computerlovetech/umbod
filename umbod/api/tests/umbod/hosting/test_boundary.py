import inspect
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from typing import get_type_hints

import pytest

import umbod.hosting as hosting
import umbod.rest as rest


def test_public_exports_and_explicit_keyword_only_signatures() -> None:
    expected_exports = {
        "AccessToken", "AppConfig", "ConnectorRegistration",
        "InMemoryGroupConnectorToolPermissions", "JwtClaims", "JwtVerificationError",
        "JwtVerifier", "MCPAuthProvider", "McpToolInvocationEvent",
        "McpToolInvocationLogSink", "OAuthService", "TokenVerifier",
        "create_mcp_app", "create_rest_app", "create_telemetry_app", "TelemetryAppConfig",
    }
    assert set(hosting.__all__) == expected_exports
    assert dir(hosting) == sorted(expected_exports)
    for name in expected_exports:
        owner = (
            "umbod.hosting.applications" if name in {"create_rest_app", "create_mcp_app"}
            else "umbod.config.telemetry" if name == "TelemetryAppConfig"
            else "umbod.rest.telemetry.application" if name == "create_telemetry_app"
            else "umbod.hosting.contracts"
        )
        original = getattr(import_module(owner), name)
        assert getattr(hosting, name) is original
        assert getattr(hosting, name) is original
        assert vars(hosting)[name] is original
    with pytest.raises(AttributeError, match="has no attribute unknown_export"):
        hosting.unknown_export
    assert not hasattr(hosting, "PublicAppConfig")
    assert not hasattr(hosting, "PublicAppRuntimeContext")
    for factory, expected_names in (
        (hosting.create_rest_app, ("settings", "connector_registrations", "admin_verifier", "oauth_service", "user_authentication")),
        (hosting.create_mcp_app, ("settings", "auth_provider", "group_permission_runtime_state", "invocation_log_sink")),
    ):
        original = getattr(import_module("umbod.hosting.applications"), factory.__name__)
        assert inspect.signature(factory) == inspect.signature(original)
        assert factory.__annotations__ == original.__annotations__
        assert get_type_hints(factory) == get_type_hints(original)
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


def test_rest_exports_preserve_original_owners_and_annotations() -> None:
    assert rest.__all__ == ["APISettings", "create_app"]
    assert dir(rest) == sorted(rest.__all__)
    for name, owner in (
        ("APISettings", "umbod.rest.settings"),
        ("create_app", "umbod.rest.main"),
    ):
        original = getattr(import_module(owner), name)
        assert getattr(rest, name) is original
        assert getattr(rest, name) is original
        assert vars(rest)[name] is original
    original_factory = import_module("umbod.rest.main").create_app
    assert inspect.signature(rest.create_app) == inspect.signature(original_factory)
    assert rest.create_app.__annotations__ == original_factory.__annotations__
    assert get_type_hints(rest.create_app) == get_type_hints(original_factory)
    with pytest.raises(AttributeError, match="has no attribute unknown_export"):
        rest.unknown_export


def test_telemetry_export_preserves_original_signature_and_annotations() -> None:
    original = import_module("umbod.rest.telemetry.application").create_telemetry_app
    assert hosting.create_telemetry_app is original
    assert inspect.signature(hosting.create_telemetry_app) == inspect.signature(original)
    assert hosting.create_telemetry_app.__annotations__ == original.__annotations__
    assert get_type_hints(hosting.create_telemetry_app) == get_type_hints(original)


def test_import_does_not_read_environment_or_create_applications(tmp_path: Path) -> None:
    program = """
import os
import sys

before = dict(os.environ)
import umbod.hosting as hosting
assert "umbod.hosting.applications" not in sys.modules
assert "umbod.hosting.contracts" not in sys.modules
assert not any(name == "umbod.config" or name.startswith("umbod.config.") for name in sys.modules)
assert dict(os.environ) == before

from umbod.hosting.shutdown import ProcessShutdownDeadline
assert not any(
    name == prefix or name.startswith(prefix + ".")
    for prefix in ("fastapi", "uvicorn", "umbod.rest", "umbod.mcp")
    for name in sys.modules
)
assert "umbod.hosting.applications" not in sys.modules

import umbod.rest as rest
assert "umbod.rest.main" not in sys.modules
assert "umbod.rest.settings" not in sys.modules

import umbod.config as config
config.load_app_config = config.load_server_app_config = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("config loaded"))

import umbod.cli.main
assert "umbod.hosting.api_server" not in sys.modules
assert "umbod.hosting.applications" not in sys.modules
assert "umbod.rest.main" not in sys.modules
assert "umbod.mcp.public_app" not in sys.modules

from umbod.rest.settings import APISettings
assert rest.APISettings is APISettings
assert "umbod.rest.main" not in sys.modules

import umbod.hosting.telemetry_service
assert "umbod.rest.main" not in sys.modules
assert "umbod.mcp.public_app" not in sys.modules
assert hosting.create_telemetry_app is umbod.hosting.telemetry_service.create_telemetry_app

import umbod.hosting.api_server as api_server
assert api_server.ProcessShutdownDeadline is ProcessShutdownDeadline
assert "umbod.mcp.public_app" not in sys.modules
assert "umbod.hosting.applications" not in sys.modules
from umbod.rest.main import create_app
assert rest.create_app is create_app

from umbod.hosting import create_rest_app
from umbod.hosting.applications import create_rest_app as original_rest, create_mcp_app
assert create_rest_app is original_rest
assert hosting.create_mcp_app is create_mcp_app
assert "umbod.hosting.mcp_service" not in sys.modules
assert "umbod.hosting.rest_service" not in sys.modules
assert dict(os.environ) == before
"""
    result = subprocess.run([sys.executable, "-c", program], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
