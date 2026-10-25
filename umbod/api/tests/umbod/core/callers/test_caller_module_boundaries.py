import ast
import subprocess
import sys
from pathlib import Path


CALLERS_ROOT = Path(__file__).parents[4] / "src" / "umbod" / "core" / "callers"


def test_caller_contracts_are_independent_of_delivery_configuration_and_connector_kinds() -> None:
    forbidden = (
        "fastapi", "fastmcp", "mcp", "umbod.rest", "umbod.mcp", "umbod.config",
        "umbod.infrastructure", "umbod.core.connectors",
    )
    violations: list[str] = []
    for path in CALLERS_ROOT.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            if any(module == prefix or module.startswith(prefix + ".") for module in modules for prefix in forbidden):
                violations.append(f"{path.name}:{node.lineno}")
    assert violations == []


def test_importing_caller_contracts_does_not_load_delivery_or_authentication_frameworks() -> None:
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys; import umbod.core.callers; "
            "assert not any(name.split('.')[0] in {'fastmcp', 'fastapi', 'mcp'} "
            "for name in sys.modules)"
        )],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
