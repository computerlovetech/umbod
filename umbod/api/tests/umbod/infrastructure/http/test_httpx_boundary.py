import ast
from pathlib import Path


def _imports_httpx(statement: ast.AST) -> bool:
    if isinstance(statement, ast.Import):
        return any(alias.name.split(".", 1)[0] == "httpx" for alias in statement.names)
    if isinstance(statement, ast.ImportFrom) and statement.level == 0 and statement.module:
        return statement.module.split(".", 1)[0] == "httpx"
    return False


def test_only_http_infrastructure_imports_httpx_in_production() -> None:
    source_root = Path(__file__).parents[4] / "src" / "umbod"
    allowed_directory = source_root / "infrastructure" / "http"
    violations = [
        f"{path.relative_to(source_root)}:{statement.lineno}"
        for path in sorted(source_root.rglob("*.py"))
        if not path.is_relative_to(allowed_directory)
        for statement in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(statement, (ast.Import, ast.ImportFrom)) and _imports_httpx(statement)
    ]
    assert not violations, "HTTPX imports outside HTTP infrastructure: " + ", ".join(violations)
