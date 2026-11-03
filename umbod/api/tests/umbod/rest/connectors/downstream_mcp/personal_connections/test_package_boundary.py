from pathlib import Path

from umbod import rest


def test_personal_rest_package_belongs_to_downstream_mcp() -> None:
    rest_root = Path(rest.__file__).parent
    package_root = rest_root / "connectors" / "downstream_mcp" / "personal_connections"
    assert not (rest_root / "personal_connections").exists()
    assert all((package_root / name).is_file() for name in ("__init__.py", "routes.py", "dependencies.py", "schemas.py", "oauth_routes.py", "oauth_dependencies.py", "oauth_schemas.py", "oauth_callback.py"))
