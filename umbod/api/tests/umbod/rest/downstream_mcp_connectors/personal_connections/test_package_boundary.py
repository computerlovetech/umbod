from pathlib import Path


def test_personal_rest_package_belongs_to_downstream_mcp() -> None:
    rest_root = Path(__file__).parents[5] / "src" / "umbod" / "rest"
    package_root = rest_root / "connectors" / "downstream_mcp" / "personal_connections"
    assert not (rest_root / "personal_connections").exists()
    assert all((package_root / name).is_file() for name in ("__init__.py", "routes.py", "dependencies.py", "schemas.py", "oauth_routes.py", "oauth_dependencies.py", "oauth_schemas.py", "oauth_callback.py"))
