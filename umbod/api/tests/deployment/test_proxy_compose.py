import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional


APP_ROOT = Path(__file__).parents[3]


def authentication_compose_configuration(
    overrides: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    environment = {
        **os.environ,
        "UMBOD_OIDC_DOMAIN": "login.example.test",
        "UMBOD_OIDC_CLIENT_ID": "test-client",
        "UMBOD_OIDC_CLIENT_SECRET": "test-secret",
        "UMBOD_OIDC_AUDIENCE": "https://audience.example.test",
        "UMBOD_ROOT_SECRET": "test-root-secret",
        "UMBOD_OAUTH2_PROXY_COOKIE_SECRET": "01234567890123456789012345678901",
        "UMBOD_PUBLIC_SITE_ORIGIN": "https://umbod-admin.computerlove.tech",
        "UMBOD_PUBLIC_SITE_HOST": "umbod-admin.computerlove.tech",
        "UMBOD_OAUTH2_PROXY_SCOPE": "openid email profile permissions offline_access",
        "UMBOD_OAUTH2_PROXY_COOKIE_REFRESH": "5m",
        "UMBOD_OAUTH2_PROXY_COOKIE_EXPIRE": "8h",
        "PUBLIC_AUTH0_DOMAIN": "",
        "PUBLIC_AUTH0_CLIENT_ID": "",
        "PUBLIC_LOGOUT_RETURN_URL": "",
        **(overrides or {}),
    }
    compose_path = environment.get(
        "UMBOD_PROXY_COMPOSE_FILE", str(APP_ROOT / "docker-compose.yml")
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            compose_path,
            "--profile",
            "auth",
            "config",
            "--format",
            "json",
        ],
        cwd=APP_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_admin_authentication_headers_are_aligned_across_services() -> None:
    configuration = authentication_compose_configuration()
    services = configuration["services"]
    proxy_labels = services["oauth2-proxy"]["labels"]
    api_header = services["api"]["environment"]["UMBOD_ADMIN_JWT_HEADER"]
    forwarded_headers = {
        header.strip().lower()
        for header in proxy_labels[
            "traefik.http.middlewares.umbod-auth.forwardauth.authResponseHeaders"
        ].split(",")
    }
    assert api_header.lower() in forwarded_headers
    assert "x-auth-request-access-token" in forwarded_headers
    assert proxy_labels["traefik.http.middlewares.umbod-auth.forwardauth.address"] == (
        "http://oauth2-proxy:4180/oauth2/auth"
    )
    alpha = configuration["configs"]["oauth2-proxy-alpha"]["content"]
    assert "name: X-Auth-Request-Access-Token" in alpha
    assert "claim: access_token" in alpha
    assert "name: Authorization" in alpha
    assert "name: X-Auth-Request-ID-Token" in alpha
    assert (
        "name: Authorization\n    values: [{claim: access_token, prefix: 'Bearer '}]"
        in alpha
    )
    assert "name: X-Auth-Request-ID-Token\n    values: [{claim: id_token}]" in alpha
    assert "x-auth-request-id-token" in forwarded_headers
    assert services["api"]["environment"]["UMBOD_USER_PROFILE_MODE"] == "access_claims"
    assert (
        services["frontend"]["labels"][
            "traefik.http.middlewares.umbod-browser-response.headers.customresponseheaders.X-Auth-Request-ID-Token"
        ]
        == ""
    )


def test_browser_pages_use_gateway_upstream_without_error_middleware() -> None:
    configuration = authentication_compose_configuration()
    services = configuration["services"]
    frontend_labels = services["frontend"]["labels"]
    for router in ("umbod-frontend", "umbod-frontend-secure"):
        prefix = f"traefik.http.routers.{router}"
        if f"{prefix}.rule" in frontend_labels:
            assert frontend_labels[f"{prefix}.service"] == "umbod-oauth"
            assert frontend_labels[f"{prefix}.middlewares"].split(",") in [
                ["umbod-browser-response@docker"],
                ["umbod-admin-forwarded-https@docker", "umbod-browser-response@docker"],
            ]
    assert not any(
        "umbod-auth-errors" in label
        for service in services.values()
        for label in service.get("labels", {})
    )
    alpha = configuration["configs"]["oauth2-proxy-alpha"]["content"]
    assert "BindAddress: 0.0.0.0:4180" in alpha
    assert "uri: http://frontend:3000/" in alpha
    assert "static://" not in alpha


def test_browser_api_uses_authenticated_python_router_without_html_redirect() -> None:
    services = authentication_compose_configuration()["services"]
    api_labels = services["api"]["labels"]
    for router in ("umbod-browser-api", "umbod-browser-api-secure"):
        prefix = f"traefik.http.routers.{router}"
        if f"{prefix}.rule" in api_labels:
            assert api_labels[f"{prefix}.rule"] == (
                "Host(`umbod-admin.computerlove.tech`) && PathPrefix(`/api/`)"
            )
            assert api_labels[f"{prefix}.middlewares"].split(",") in [
                ["umbod-browser-response@docker", "umbod-auth@docker"],
                [
                    "umbod-admin-forwarded-https@docker",
                    "umbod-browser-response@docker",
                    "umbod-auth@docker",
                ],
            ]
            assert api_labels[f"{prefix}.service"] == "umbod-browser-api"
            assert api_labels[f"{prefix}.priority"] == "50"
    assert (
        api_labels["traefik.http.services.umbod-browser-api.loadbalancer.server.port"]
        == "8000"
    )
    assert not any("stripprefix" in label.lower() for label in api_labels)


def test_public_signed_out_and_favicon_routes_bypass_authentication() -> None:
    services = authentication_compose_configuration()["services"]
    labels = services["frontend"]["labels"]
    for router in ("umbod-signed-out", "umbod-signed-out-secure"):
        prefix = f"traefik.http.routers.{router}"
        assert labels[f"{prefix}.rule"] == (
            "Host(`umbod-admin.computerlove.tech`) && Path(`/signed-out.html`)"
        )
        assert labels[f"{prefix}.service"] == "umbod-frontend"
        assert labels[f"{prefix}.priority"] == "20"
        assert f"{prefix}.middlewares" not in labels
    for router in ("umbod-favicon", "umbod-favicon-secure"):
        prefix = f"traefik.http.routers.{router}"
        if f"{prefix}.rule" in labels:
            assert labels[f"{prefix}.service"] == "umbod-frontend"
            assert f"{prefix}.middlewares" not in labels
    oauth_labels = services["oauth2-proxy"]["labels"]
    assert oauth_labels["traefik.http.routers.umbod-oauth.priority"] == "100"
    assert oauth_labels["traefik.http.routers.umbod-oauth.service"] == "umbod-oauth"


def test_static_frontend_receives_only_public_configuration_and_proxy_target() -> None:
    frontend = authentication_compose_configuration(
        {
            "PUBLIC_AUTH0_DOMAIN": "login.example.test",
            "PUBLIC_AUTH0_CLIENT_ID": "test-client",
            "PUBLIC_LOGOUT_RETURN_URL": "https://umbod-admin.computerlove.tech/signed-out.html",
        }
    )["services"]["frontend"]
    environment = frontend["environment"]
    assert environment["PUBLIC_AUTH0_DOMAIN"] == "login.example.test"
    assert environment["PUBLIC_AUTH0_CLIENT_ID"] == "test-client"
    assert (
        environment["PUBLIC_LOGOUT_RETURN_URL"]
        == "https://umbod-admin.computerlove.tech/signed-out.html"
    )
    assert environment["PUBLIC_API_BASE_URL"] == "/api"
    assert set(environment).issubset(
        {
            "PUBLIC_API_BASE_URL",
            "PUBLIC_MCP_BASE_URL",
            "API_PROXY_ORIGIN",
            "PUBLIC_AUTH0_DOMAIN",
            "PUBLIC_AUTH0_CLIENT_ID",
            "PUBLIC_LOGOUT_RETURN_URL",
        }
    )
    assert "node" not in " ".join(frontend["healthcheck"]["test"])


def test_default_local_logout_configuration_is_null() -> None:
    configuration = authentication_compose_configuration(
        {
            "UMBOD_PROXY_COMPOSE_FILE": str(APP_ROOT / "docker-compose.yml"),
        }
    )
    environment = configuration["services"]["frontend"]["environment"]
    assert {
        environment[name]
        for name in (
            "PUBLIC_AUTH0_DOMAIN",
            "PUBLIC_AUTH0_CLIENT_ID",
            "PUBLIC_LOGOUT_RETURN_URL",
        )
    } == {""}
    generated = subprocess.run(
        ["sh", str(APP_ROOT / "frontend/deployment/generate-config.sh")],
        env={**os.environ, **environment},
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(generated.stdout)["logout"] is None


def test_browser_response_stripping_does_not_change_internal_forwardauth() -> None:
    services = authentication_compose_configuration()["services"]
    frontend_labels = services["frontend"]["labels"]
    stripping_prefix = (
        "traefik.http.middlewares.umbod-browser-response.headers.customresponseheaders"
    )
    headers = {
        "Authorization",
        "X-Auth-Request-Access-Token",
        "X-Auth-Request-ID-Token",
        "X-Auth-Request-User",
        "X-Auth-Request-Email",
        "X-Auth-Request-Preferred-Username",
        "X-Auth-Request-Groups",
        "X-Forwarded-Access-Token",
    }
    assert all(
        frontend_labels[f"{stripping_prefix}.{header}"] == "" for header in headers
    )
    for router in ("umbod-frontend", "umbod-frontend-secure"):
        assert frontend_labels[f"traefik.http.routers.{router}.middlewares"].split(
            ","
        ) in [
            ["umbod-browser-response@docker"],
            ["umbod-admin-forwarded-https@docker", "umbod-browser-response@docker"],
        ]
    for service in services.values():
        for label, value in service.get("labels", {}).items():
            if (
                label.endswith(".middlewares")
                and "umbod-browser-response@docker" in value
            ):
                assert label in {
                    "traefik.http.routers.umbod-frontend.middlewares",
                    "traefik.http.routers.umbod-frontend-secure.middlewares",
                    "traefik.http.routers.umbod-browser-api.middlewares",
                    "traefik.http.routers.umbod-browser-api-secure.middlewares",
                    "traefik.http.routers.umbod-oauth.middlewares",
                    "traefik.http.routers.umbod-oauth-secure.middlewares",
                }
    for service_name, routers in (
        ("api", ("umbod-browser-api", "umbod-browser-api-secure")),
        ("oauth2-proxy", ("umbod-oauth", "umbod-oauth-secure")),
    ):
        labels = services[service_name]["labels"]
        for router in routers:
            prefix = f"traefik.http.routers.{router}"
            if f"{prefix}.rule" not in labels:
                continue
            middleware = labels[f"{prefix}.middlewares"].split(",")
            assert "umbod-browser-response@docker" in middleware
            if service_name == "api":
                assert middleware.index(
                    "umbod-browser-response@docker"
                ) < middleware.index("umbod-auth@docker")
            else:
                assert "umbod-auth@docker" not in middleware
    oauth_labels = services["oauth2-proxy"]["labels"]
    assert "X-Auth-Request-Access-Token" in oauth_labels[
        "traefik.http.middlewares.umbod-auth.forwardauth.authResponseHeaders"
    ].split(",")
    assert oauth_labels[
        "traefik.http.middlewares.umbod-auth.forwardauth.address"
    ].endswith("/oauth2/auth")


def test_alpha_provider_fixes_audience_and_does_not_mix_legacy_flags() -> None:
    configuration = authentication_compose_configuration()
    proxy = configuration["services"]["oauth2-proxy"]
    command = proxy["command"]
    alpha = configuration["configs"]["oauth2-proxy-alpha"]["content"]
    assert "--alpha-config=/etc/oauth2-proxy/alpha.yml" in command
    assert {
        "source": "oauth2-proxy-alpha",
        "target": "/etc/oauth2-proxy/alpha.yml",
    }.items() <= proxy["configs"][0].items()
    assert "audienceClaims: [aud]" in alpha
    assert "emailClaim: email" in alpha
    assert "issuerURL: https://login.example.test/" in alpha
    assert "clientID:" in alpha and "test-client" in alpha
    assert "${UMBOD_OIDC_CLIENT_SECRET}" in alpha
    assert "test-secret" not in alpha
    assert proxy["environment"]["UMBOD_OIDC_CLIENT_SECRET"] == "test-secret"
    assert 'name: audience\n        default: ["https://audience.example.test"]' in alpha
    assert "allow:" not in alpha
    forbidden = (
        "--http-address=",
        "--provider=",
        "--oidc-",
        "--client-",
        "--scope=",
        "--login-url=",
        "--upstream=",
        "--pass-access-token=",
        "--set-xauthrequest=",
        "--set-authorization-header=",
        "--pass-authorization-header=",
        "--auth-request-extra-params=",
    )
    assert not any(option.startswith(forbidden) for option in command)
    assert {
        option for option in command if option.startswith("--whitelist-domain=")
    } == {
        "--whitelist-domain=login.example.test",
        "--whitelist-domain=umbod-admin.computerlove.tech",
    }
    assert "--cookie-refresh=5m" in command
    assert "--cookie-expire=8h" in command
    assert "offline_access" in alpha


def test_https_gateway_contract_preserves_secure_csrf_cookie_configuration() -> None:
    services = authentication_compose_configuration()["services"]
    proxy = services["oauth2-proxy"]
    labels = proxy["labels"]
    prefix = "traefik.http.middlewares.umbod-admin-forwarded-https.headers.customrequestheaders"
    if f"{prefix}.X-Forwarded-Proto" not in labels:
        return
    assert labels[f"{prefix}.X-Forwarded-Proto"] == "https"
    assert labels[f"{prefix}.X-Forwarded-Port"] == "443"
    assert {
        "--cookie-secure=true",
        "--cookie-httponly=true",
        "--cookie-samesite=lax",
        "--cookie-path=/",
    }.issubset(proxy["command"])
    for service, routers in (
        ("oauth2-proxy", ("umbod-oauth", "umbod-oauth-secure")),
        ("frontend", ("umbod-frontend", "umbod-frontend-secure")),
        ("api", ("umbod-browser-api", "umbod-browser-api-secure")),
    ):
        for router in routers:
            middleware = services[service]["labels"][
                f"traefik.http.routers.{router}.middlewares"
            ].split(",")
            assert middleware[0] == "umbod-admin-forwarded-https@docker"
