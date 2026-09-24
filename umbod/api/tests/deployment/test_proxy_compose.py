import json
import subprocess
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).parents[3]


def authentication_compose_configuration() -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "compose", "--profile", "auth", "config", "--format", "json"],
        cwd=APP_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_admin_authentication_headers_are_aligned_across_production_services() -> None:
    configuration = authentication_compose_configuration()
    services = configuration["services"]
    oauth2_proxy = services["oauth2-proxy"]
    oauth2_proxy_labels = oauth2_proxy["labels"]
    frontend = services["frontend"]
    api = services["api"]

    expected_header = frontend["environment"]["PRIVATE_AUTH_TOKEN_HEADER"]
    api_header = api["environment"]["UMBOD_ADMIN_JWT_HEADER"]
    forwarded_headers = {
        header.strip().lower()
        for header in oauth2_proxy_labels[
            "traefik.http.middlewares.umbod-auth.forwardauth.authResponseHeaders"
        ].split(",")
    }

    assert expected_header == api_header
    assert expected_header.lower() in forwarded_headers
    assert "x-auth-request-access-token" in forwarded_headers
    assert "umbod-auth@docker" in frontend["labels"][
        "traefik.http.routers.umbod-frontend.middlewares"
    ].split(",")
    assert (
        oauth2_proxy_labels["traefik.http.middlewares.umbod-auth.forwardauth.address"]
        == "http://oauth2-proxy:4180/"
    )
    assert {
        "--set-authorization-header=true",
        "--set-xauthrequest=true",
        "--pass-access-token=true",
        "--pass-authorization-header=true",
    }.issubset(oauth2_proxy["command"])


def test_expired_proxy_sessions_are_sent_to_sign_in() -> None:
    configuration = authentication_compose_configuration()
    services = configuration["services"]
    oauth2_proxy_labels = services["oauth2-proxy"]["labels"]
    frontend_labels = services["frontend"]["labels"]
    middleware_prefix = "traefik.http.middlewares.umbod-auth-errors.errors"

    assert (
        frontend_labels["traefik.http.routers.umbod-frontend.middlewares"]
        == "umbod-auth-errors@docker,umbod-auth@docker"
    )
    assert oauth2_proxy_labels[f"{middleware_prefix}.status"] == "401"
    assert oauth2_proxy_labels[f"{middleware_prefix}.service"] == "umbod-oauth"
    assert oauth2_proxy_labels[f"{middleware_prefix}.query"] == "/oauth2/sign_in?rd={url}"


def test_oauth_proxy_refreshes_sessions_before_access_tokens_expire() -> None:
    configuration = authentication_compose_configuration()
    oauth2_proxy = configuration["services"]["oauth2-proxy"]

    assert "--cookie-refresh=5m" in oauth2_proxy["command"]
    assert "--cookie-expire=8h" in oauth2_proxy["command"]
    assert (
        "offline_access"
        in next(
            option for option in oauth2_proxy["command"] if option.startswith("--scope=")
        ).split()
    )
