import json
import subprocess
from pathlib import Path

import pytest


FRONTEND_ROOT = Path(__file__).parents[3] / "frontend"


@pytest.mark.parametrize(
    "public_environment,expected",
    [
        ({}, {"apiBaseUrl": "/api", "mcpBaseUrl": "/mcp"}),
        (
            {"PUBLIC_API_BASE_URL": '/api/"quoted"\\path\nnext', "PUBLIC_MCP_BASE_URL": 'https://mcp.invalid/\t"value"'},
            {"apiBaseUrl": '/api/"quoted"\\path\nnext', "mcpBaseUrl": 'https://mcp.invalid/\t"value"'},
        ),
    ],
)
def test_runtime_configuration_contains_only_json_escaped_public_values(
    public_environment: dict[str, str], expected: dict[str, str]
) -> None:
    result = subprocess.run(
        ["/bin/sh", str(FRONTEND_ROOT / "deployment" / "generate-config.sh")],
        env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "PRIVATE_SECRET": "never-public", **public_environment},
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == expected
    assert "never-public" not in result.stdout


def test_frontend_image_runtime_has_no_node_or_application_dependencies() -> None:
    dockerfile = (FRONTEND_ROOT / "Dockerfile").read_text()
    runtime = dockerfile.split("FROM nginx:", maxsplit=1)[1]

    assert "node_modules" not in runtime
    assert "node:" not in dockerfile
    assert "USER nginx" in runtime
    assert "EXPOSE 3000" in runtime
    assert "/app/build /usr/share/nginx/html" in runtime
    assert "rm -rf /usr/share/nginx/html/*" in runtime


def test_nginx_routes_assets_api_and_health_outside_spa_fallback() -> None:
    configuration = (FRONTEND_ROOT / "deployment" / "default.conf.template").read_text()

    assert "location /_app/immutable/ {\n        try_files $uri =404;" in configuration
    assert "location /_app/ {\n        try_files $uri =404;" in configuration
    assert '"public, max-age=31536000, immutable"' in configuration
    assert "try_files $uri $uri/ /200.html;" in configuration
    assert 'Cache-Control "no-store" always;' in configuration
    assert "location = /system/health" in configuration
    assert 'return 200 \'{"status":"ok","service":"umbod-frontend"}\';' in configuration
    assert "proxy_pass $api_proxy_origin$request_uri;" in configuration
    assert "proxy_set_header Authorization $http_authorization;" in configuration
    assert "proxy_set_header Cookie $http_cookie;" in configuration
    assert "proxy_set_header Origin $http_origin;" in configuration
    assert "resolver ${DNS_RESOLVER} ipv6=off;" in configuration
    assert "client_max_body_size 12m;" in configuration
    startup = (FRONTEND_ROOT / "deployment" / "start.sh").read_text()
    assert "/etc/resolv.conf" in startup
    assert "${API_PROXY_ORIGIN} ${DNS_RESOLVER}" in startup
