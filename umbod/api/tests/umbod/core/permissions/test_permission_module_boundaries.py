import ast
import subprocess
import sys
from pathlib import Path

import pytest


def test_permissions_core_does_not_import_delivery_frameworks() -> None:
    root = Path(__file__).parents[4] / "src" / "umbod" / "core" / "permissions"
    forbidden = ("fastmcp", "mcp", "umbod.mcp", "umbod.rest")
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


@pytest.mark.parametrize("public_name", [
    "ConnectorCapabilityPermission",
    "ConnectorToolPermission",
    "GroupConnectorToolPermissionState",
    "InMemoryGroupConnectorToolPermissions",
])
def test_public_permission_runtime_import_does_not_load_delivery_frameworks(public_name: str) -> None:
    program = (
        f"from umbod.core.permissions import {public_name}; import sys; "
        "prefixes = ('fastmcp', 'mcp', 'umbod.mcp', 'umbod.rest'); "
        "loaded = [name for name in sys.modules "
        "if any(name == prefix or name.startswith(prefix + '.') for prefix in prefixes)]; "
        "raise SystemExit(','.join(loaded) if loaded else 0)"
    )
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
