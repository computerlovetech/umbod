import ast
import subprocess
import sys
from pathlib import Path


def test_analytics_contracts_do_not_import_backend_or_delivery_modules() -> None:
    root = Path(__file__).parents[4] / "src" / "umbod" / "core" / "telemetry" / "analytics"
    forbidden = (
        "duckdb", "clickhouse_connect", "psycopg", "sqlite3", "sqlalchemy",
        "umbod.infrastructure", "umbod.config", "umbod.rest", "umbod.mcp",
    )
    violations: list[str] = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden):
                    violations.append(f"{path}:{node.lineno}:{module}")

    assert violations == []


def test_importing_analytics_contracts_does_not_load_infrastructure() -> None:
    program = (
        "import sys, umbod.core.telemetry.analytics; "
        "loaded = [name for name in sys.modules if name.startswith('umbod.infrastructure')]; "
        "raise SystemExit(','.join(loaded) if loaded else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=False,
    )

    assert result.returncode == 0, result.stderr
