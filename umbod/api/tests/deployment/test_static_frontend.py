import json
import subprocess
from pathlib import Path

import pytest


FRONTEND_ROOT = Path(__file__).parents[3] / "frontend"


@pytest.mark.parametrize(
    "public_environment,expected",
    [
        ({}, {"apiBaseUrl": "/api", "mcpBaseUrl": "/mcp", "logout": None}),
        (
            {"PUBLIC_API_BASE_URL": '/api/"quoted"\\path\nnext', "PUBLIC_MCP_BASE_URL": 'https://mcp.invalid/\t"value"'},
            {"apiBaseUrl": '/api/"quoted"\\path\nnext', "mcpBaseUrl": 'https://mcp.invalid/\t"value"', "logout": None},
        ),
    ],
)
def test_runtime_configuration_contains_only_json_escaped_public_values(
    public_environment: dict[str, str], expected: dict[str, object]
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


def test_runtime_logout_configuration_safely_encodes_public_client() -> None:
    environment = {
        "PUBLIC_AUTH0_DOMAIN": "tenant.eu.auth0.com",
        "PUBLIC_AUTH0_CLIENT_ID": 'actual-client&=+"',
        "PUBLIC_LOGOUT_RETURN_URL": "https://admin.example.test/signed-out.html",
    }
    result = subprocess.run(
        ["/bin/sh", str(FRONTEND_ROOT / "deployment" / "generate-config.sh")],
        env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "PRIVATE_SECRET": "never-public", **environment},
        check=True, capture_output=True, text=True,
    )
    assert json.loads(result.stdout)["logout"] == {
        "auth0Domain": environment["PUBLIC_AUTH0_DOMAIN"],
        "clientId": environment["PUBLIC_AUTH0_CLIENT_ID"],
        "returnTo": environment["PUBLIC_LOGOUT_RETURN_URL"],
    }
    assert "never-public" not in result.stdout


@pytest.mark.parametrize("override", [
    {"PUBLIC_AUTH0_DOMAIN": ""},
    {"PUBLIC_AUTH0_DOMAIN": "https://tenant.auth0.com"},
    {"PUBLIC_AUTH0_DOMAIN": "tenant.auth0.com:443"},
    {"PUBLIC_AUTH0_DOMAIN": "user@tenant.auth0.com"},
    {"PUBLIC_AUTH0_DOMAIN": "tenant.auth0.com/path"},
    {"PUBLIC_AUTH0_DOMAIN": "*.auth0.com"},
    {"PUBLIC_AUTH0_DOMAIN": "tenant.auth0.com\n"},
    {"PUBLIC_AUTH0_CLIENT_ID": ""},
    {"PUBLIC_AUTH0_CLIENT_ID": "a" * 257},
    {"PUBLIC_AUTH0_CLIENT_ID": "bad\tclient"},
    {"PUBLIC_AUTH0_CLIENT_ID": "bad\x01client"},
    {"PUBLIC_LOGOUT_RETURN_URL": ""},
    {"PUBLIC_LOGOUT_RETURN_URL": "http://admin.example.test/signed-out.html"},
    {"PUBLIC_LOGOUT_RETURN_URL": "https://user@admin.example.test/signed-out.html"},
    {"PUBLIC_LOGOUT_RETURN_URL": "https://admin.example.test/signed-out.html?evil"},
    {"PUBLIC_LOGOUT_RETURN_URL": "https://admin.example.test/signed-out.html#evil"},
    {"PUBLIC_LOGOUT_RETURN_URL": "https://admin.example.test/admin"},
    {"PUBLIC_LOGOUT_RETURN_URL": "https://admin.example.test/a/../signed-out.html"},
    {"PUBLIC_LOGOUT_RETURN_URL": "https://admin.example.test:99999/signed-out.html"},
])
def test_runtime_logout_configuration_rejects_partial_or_unsafe_values(override: dict[str, str]) -> None:
    result = subprocess.run(
        ["/bin/sh", str(FRONTEND_ROOT / "deployment" / "generate-config.sh")],
        env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin",
             "PUBLIC_AUTH0_DOMAIN": "tenant.auth0.com",
             "PUBLIC_AUTH0_CLIENT_ID": "actual-client",
             "PUBLIC_LOGOUT_RETURN_URL": "https://admin.example.test/signed-out.html", **override},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "Invalid public logout configuration" in result.stderr
    assert "actual-client" not in result.stderr


def test_signed_out_page_is_independent_and_requires_explicit_sign_in() -> None:
    page = (FRONTEND_ROOT / "static" / "signed-out.html").read_text()
    assert '<html lang="en">' in page
    assert '<h1>Signed out</h1>' in page
    assert 'href="/oauth2/sign_in?rd=%2Fadmin"' in page
    assert "does not revoke existing tokens" in page
    for dependency in ["<script", "<link", "app-config", "/api", "http-equiv", "@import", "url("]:
        assert dependency not in page


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
    assert 'location = /signed-out.html {\n        try_files $uri =404;\n        add_header Cache-Control "no-store" always;' in configuration
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
