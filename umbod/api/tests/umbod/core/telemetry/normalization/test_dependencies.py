import ast
from importlib.util import resolve_name
from pathlib import Path

from umbod.core.telemetry import normalization


def _imported_modules(node: ast.AST, package: str) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level:
            module = resolve_name("." * node.level + module, package)
        return (module, *(f"{module}.{alias.name}" for alias in node.names))
    return ()


def test_canonical_normalization_package_never_imports_downstream_analytics() -> None:
    root = Path(normalization.__file__).parent
    violations: list[str] = []
    for source in root.rglob("*.py"):
        relative_package = source.parent.relative_to(root).parts
        package = ".".join((normalization.__name__, *relative_package))
        for node in ast.walk(ast.parse(source.read_text())):
            for module in _imported_modules(node, package):
                if module == "umbod.core.telemetry.analytics" or module.startswith("umbod.core.telemetry.analytics."):
                    violations.append(f"{source.name}: {module}")
    assert violations == []
