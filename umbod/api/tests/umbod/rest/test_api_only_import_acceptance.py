import subprocess
from pathlib import Path


def test_rest_permission_and_openapi_composition_imports_with_api_only_dependencies() -> None:
    api_root = Path(__file__).parents[3]
    result = subprocess.run(
        [
            "uv",
            "run",
            "--isolated",
            "--frozen",
            "--no-default-groups",
            "--group",
            "shared",
            "--group",
            "api",
            "--",
            "python",
            "-c",
            (
                "from umbod.rest.mcp_permissions import router as permissions_router; "
                "from umbod.rest.connectors.openapi import router as openapi_router; "
                "from umbod.rest.main import create_app"
            ),
        ],
        cwd=api_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
