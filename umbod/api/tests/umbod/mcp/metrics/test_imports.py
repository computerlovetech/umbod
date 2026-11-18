import subprocess
import sys


def test_observation_contracts_import_without_exporter_or_http_dependencies() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "import umbod.mcp.metrics\n"
            "blocked = ('prometheus_client', 'starlette', 'uvicorn', 'umbod.infrastructure.metrics')\n"
            "assert not [name for name in sys.modules "
            "if any(name == prefix or name.startswith(prefix + '.') for prefix in blocked)]\n",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
