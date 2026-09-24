from umbod.config.operator import OperatorSettings

_VALID_PROFILES = ("local", "production")
_VALID_AUTH_RECIPES = ("none", "dev", "auth0", "entra", "google")
_OIDC_AUTH_RECIPES = ("auth0", "entra", "google")


def resolve_auth_recipe(operator: OperatorSettings) -> str:
    if operator.profile not in _VALID_PROFILES:
        raise ValueError(
            f"UMBOD_PROFILE must be one of {', '.join(_VALID_PROFILES)} (got '{operator.profile}')"
        )
    auth = (
        operator.auth
        if operator.auth is not None
        else ("dev" if operator.profile == "local" else None)
    )
    if auth is None:
        raise ValueError(
            "UMBOD_AUTH must be one of auth0, entra, google when UMBOD_PROFILE is production"
        )
    if auth not in _VALID_AUTH_RECIPES:
        raise ValueError(
            f"UMBOD_AUTH must be one of {', '.join(_VALID_AUTH_RECIPES)} (got '{auth}')"
        )
    if operator.profile == "production" and auth in ("none", "dev"):
        raise ValueError(
            f"UMBOD_AUTH={auth} is not allowed when UMBOD_PROFILE is production"
        )
    return auth


def _validate_oidc_recipe(operator: OperatorSettings, auth_recipe: str) -> None:
    if not operator.oidc_client_id.strip():
        raise ValueError(
            f"UMBOD_OIDC_CLIENT_ID is required for UMBOD_AUTH={auth_recipe}"
        )
    if auth_recipe == "auth0":
        if not operator.oidc_domain.strip() and not operator.oidc_config_url.strip():
            raise ValueError("UMBOD_OIDC_DOMAIN is required for UMBOD_AUTH=auth0")
        if not operator.oidc_audience.strip():
            raise ValueError("UMBOD_OIDC_AUDIENCE is required for UMBOD_AUTH=auth0")
        if not operator.oidc_client_secret.strip():
            raise ValueError(
                "UMBOD_OIDC_CLIENT_SECRET is required for UMBOD_AUTH=auth0"
            )
    if auth_recipe == "entra":
        if not operator.oidc_tenant_id.strip():
            raise ValueError(
                "UMBOD_OIDC_TENANT_ID is required for UMBOD_AUTH=entra"
            )
        if not operator.oidc_required_scopes:
            raise ValueError(
                "UMBOD_OIDC_REQUIRED_SCOPES is required for UMBOD_AUTH=entra"
            )


def validate_operator(operator: OperatorSettings, auth_recipe: str) -> None:
    ports = (
        ("UMBOD_REST_PORT", operator.rest_port),
        ("UMBOD_REST_METRICS_PORT", operator.rest_metrics_port),
        ("UMBOD_MCP_PORT", operator.mcp_port),
        ("UMBOD_MCP_METRICS_PORT", operator.mcp_metrics_port),
    )
    for index, (name, port) in enumerate(ports):
        for other_name, other_port in ports[index + 1 :]:
            if port == other_port:
                raise ValueError(f"{other_name} must be distinct from {name}")
    if operator.profile == "production" and not operator.root_secret.strip():
        raise ValueError("UMBOD_ROOT_SECRET is required in production")
    if auth_recipe in _OIDC_AUTH_RECIPES:
        _validate_oidc_recipe(operator, auth_recipe)
        return
    if auth_recipe == "dev" and not operator.mcp_test_bearer_token.strip():
        raise ValueError(
            "UMBOD_MCP_TEST_BEARER_TOKEN must be set when UMBOD_AUTH is dev"
        )
