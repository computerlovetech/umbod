import ast
import subprocess
import sys
from pathlib import Path

import pytest


def test_filesystem_core_contains_no_backend_configuration_or_adapter_package() -> None:
    root = Path(__file__).parents[4] / "src" / "umbod" / "core" / "filesystem"

    assert not (root / "adapters").exists()
    assert not (root / "config.py").exists()


def test_filesystem_core_does_not_import_host_filesystem_or_infrastructure() -> None:
    root = Path(__file__).parents[4] / "src" / "umbod" / "core" / "filesystem"
    forbidden = ("os", "fcntl", "tempfile", "pathlib", "sqlite3", "umbod.infrastructure")
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


@pytest.mark.parametrize("module", [
    "umbod.core.filesystem",
    "umbod.core.filesystem.models",
    "umbod.core.filesystem.ports",
    "umbod.core.filesystem.errors",
    "umbod.core.filesystem.namespace",
    "umbod.core.filesystem.service",
    "umbod.core.filesystem.stores",
    "umbod.core.filesystem.stores.schema",
    "umbod.core.filesystem.stores.namespace",
    "umbod.core.filesystem.stores.access_control",
    "umbod.core.filesystem.stores.session",
])
def test_importing_filesystem_core_does_not_load_infrastructure(module: str) -> None:
    program = (
        f"import importlib, sys; importlib.import_module({module!r}); "
        "loaded = [name for name in sys.modules if name.startswith('umbod.infrastructure')]; "
        "raise SystemExit(','.join(loaded) if loaded else 0)"
    )
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr


def test_importing_infrastructure_composition_does_not_load_concrete_filesystem_drivers() -> None:
    program = (
        "import sys, umbod.infrastructure; "
        "forbidden = {'umbod.infrastructure.filesystem.inmemory', "
        "'umbod.infrastructure.filesystem.local_content'}; "
        "loaded = forbidden.intersection(sys.modules); "
        "raise SystemExit(','.join(sorted(loaded)) if loaded else 0)"
    )
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
