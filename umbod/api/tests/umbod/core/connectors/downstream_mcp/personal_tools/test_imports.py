import subprocess
import sys


def test_personal_tool_ports_import_without_prior_store_initialization() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from umbod.core.connectors.downstream_mcp.personal.tools.ports import PersonalToolDiscoveryReader"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
