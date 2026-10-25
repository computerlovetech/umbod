import subprocess
import sys


def test_personal_identity_policy_import_does_not_initialize_configuration_or_frameworks() -> None:
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys; "
            "from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal; "
            "prefixes = ('fastapi', 'fastmcp', 'mcp', 'umbod.config', 'umbod.rest', 'umbod.mcp'); "
            "loaded = [name for name in sys.modules "
            "if any(name == prefix or name.startswith(prefix + '.') for prefix in prefixes)]; "
            "assert not loaded, loaded"
        )],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
