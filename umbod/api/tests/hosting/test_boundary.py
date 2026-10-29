import inspect
import subprocess
import sys
from pathlib import Path

import umbod.hosting as hosting

def test_public_exports_and_explicit_keyword_only_signatures() -> None:
    expected_exports = {
        "AccessToken", "AppConfig", "ConnectorRegistration",
        "InMemoryGroupConnectorToolPermissions", "JwtClaims", "JwtVerificationError",
        "JwtVerifier", "MCPAuthProvider", "McpToolInvocationEvent",
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
