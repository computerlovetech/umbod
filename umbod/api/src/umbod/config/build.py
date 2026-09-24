from umbod.config import defaults
from umbod.config.app import (
    AdminAuthConfig,
    AppConfig,
    ConnectorSecurityConfig,
    ConnectorStoreConfig,
    CorsConfig,
    EndpointsConfig,
    FeatureTogglesConfig,
    McpConfig,
    OAuthStorageConfig,
    OidcConfig,
    OpenApiConnectorConfig,
    RestConfig,
    RuntimeConfig,
)
from umbod.config.operator import OperatorSettings
from umbod.config.secret_derivation import derive_secret
from umbod.config.validate import _OIDC_AUTH_RECIPES

_PROVIDER_BY_RECIPE = {
    "auth0": "auth0",
    "entra": "azure_entra_id",
    "google": "google",
}


def _default_permission_claim(auth_recipe: str) -> str:
    if auth_recipe == "auth0":
        return defaults.AUTH0_PERMISSION_GROUP_CLAIM
    return defaults.PERMISSION_GROUP_CLAIM


def _admin_membership_claim(operator: OperatorSettings, auth_recipe: str) -> str:
    if operator.admin_membership_claim is not None:
        return operator.admin_membership_claim
    return _default_permission_claim(auth_recipe)


def _mcp_permission_claim(operator: OperatorSettings, auth_recipe: str) -> str:
    if operator.mcp_permission_claim is not None:
        return operator.mcp_permission_claim
    return _default_permission_claim(auth_recipe)


def _sqlite_path(operator: OperatorSettings) -> str:
    if operator.connector_store_sqlite_path is not None:
        return operator.connector_store_sqlite_path
    return f"{operator.data_dir.rstrip('/')}/umbod.sqlite3"


def _oauth_storage_directory(operator: OperatorSettings) -> str:
    if operator.oauth_storage_directory is not None:
        return operator.oauth_storage_directory
    return f"{operator.data_dir.rstrip('/')}/fastmcp-oauth"


def _cors_origins(operator: OperatorSettings) -> list[str]:
    if operator.cors_origins:
        return operator.cors_origins
    return [operator.public_site_origin]


def _purpose_secret(root_secret: str, purpose: str) -> str:
    if not root_secret.strip():
        return ""
    return derive_secret(root_secret, purpose)


def _derived_jwks_url(operator: OperatorSettings, auth_recipe: str) -> str:
    if operator.admin_jwks_url:
        return operator.admin_jwks_url
    if auth_recipe == "auth0":
        return f"https://{operator.oidc_domain}/.well-known/jwks.json"
    if auth_recipe == "entra":
        return f"https://login.microsoftonline.com/{operator.oidc_tenant_id}/discovery/v2.0/keys"
    if auth_recipe == "google":
        return "https://www.googleapis.com/oauth2/v3/certs"
    return ""


def _derived_config_url(operator: OperatorSettings, auth_recipe: str) -> str:
    if operator.oidc_config_url:
        return operator.oidc_config_url
    if auth_recipe == "auth0":
        return f"https://{operator.oidc_domain}/.well-known/openid-configuration"
    return ""


def _derived_issuer_url(operator: OperatorSettings) -> str:
    return operator.oidc_issuer_url


def _build_admin_auth(operator: OperatorSettings, auth_recipe: str) -> AdminAuthConfig:
    environment = "production" if operator.profile == "production" else "development"
    mode = "disabled" if auth_recipe == "none" else "simulation" if auth_recipe == "dev" else "jwt"
    return AdminAuthConfig(
        environment=environment,
        mode=mode,
        jwt_header_name=operator.admin_jwt_header_name,
        jwks_url=_derived_jwks_url(operator, auth_recipe),
        membership_claim=_admin_membership_claim(operator, auth_recipe),
        required_membership=operator.admin_group,
        simulated_admin=operator.admin_simulated_admin,
        simulated_user_id=operator.admin_simulated_user_id,
        simulated_user_email=operator.admin_simulated_user_email,
        simulated_user_name=operator.admin_simulated_user_name,
        debug_enabled=operator.admin_debug_enabled,
    )


def _build_mcp(operator: OperatorSettings, auth_recipe: str) -> McpConfig:
    return McpConfig(
        port=operator.mcp_port,
        metrics_port=operator.mcp_metrics_port,
        messaging_transport=operator.mcp_messaging_transport,
        connector_tool_exposure_mode=operator.mcp_tool_exposure,
        connector_code_execution_timeout_seconds=operator.mcp_code_execution_timeout_seconds,
        maximum_uploaded_file_bytes=operator.mcp_maximum_uploaded_file_bytes,
        downstream_oauth_enabled=operator.mcp_downstream_oauth_enabled,
        downstream_discovery_enabled=operator.mcp_downstream_discovery_enabled,
        downstream_discovery_timeout_seconds=operator.mcp_downstream_discovery_timeout_seconds,
        downstream_refresh_interval_seconds=operator.mcp_downstream_refresh_interval_seconds,
        downstream_discovery_concurrency=operator.mcp_downstream_discovery_concurrency,
        downstream_discovery_jitter_ratio=operator.mcp_downstream_discovery_jitter_ratio,
        downstream_discovery_maximum_backoff_seconds=operator.mcp_downstream_discovery_maximum_backoff_seconds,
        auth_mode=(
            "none"
            if auth_recipe == "none"
            else "single_test_user"
            if auth_recipe == "dev"
            else "oidc"
        ),
        test_user_email=operator.mcp_test_user_email,
        test_bearer_token=operator.mcp_test_bearer_token,
        test_user_group=operator.mcp_test_user_group,
        permission_group_claim=_mcp_permission_claim(operator, auth_recipe),
        auth_debug_enabled=operator.mcp_auth_debug_enabled,
        stateless_http=operator.mcp_stateless_http,
    )


def _build_oidc(operator: OperatorSettings, auth_recipe: str) -> OidcConfig:
    if auth_recipe not in _OIDC_AUTH_RECIPES:
        return OidcConfig()
    return OidcConfig(
        provider=_PROVIDER_BY_RECIPE[auth_recipe],
        config_url=_derived_config_url(operator, auth_recipe),
        issuer_url=_derived_issuer_url(operator),
        client_id=operator.oidc_client_id,
        client_secret=operator.oidc_client_secret,
        audience=operator.oidc_audience,
        tenant_id=operator.oidc_tenant_id,
        required_scopes=operator.oidc_required_scopes,
        jwt_signing_key=_purpose_secret(operator.root_secret, "jwt-signing"),
    )


def assemble_app_config(operator: OperatorSettings, auth_recipe: str) -> AppConfig:
    return AppConfig(
        runtime=RuntimeConfig(
            app_name=operator.app_name,
            log_level=operator.log_level,
            profile=operator.profile,
            auth=auth_recipe,
        ),
        endpoints=EndpointsConfig(
            site_base_url=operator.public_site_origin,
            api_base_url=operator.public_api_origin,
            private_api_base_url=operator.internal_api_origin,
            mcp_base_url=operator.public_mcp_origin,
        ),
        rest=RestConfig(port=operator.rest_port, metrics_port=operator.rest_metrics_port),
        mcp=_build_mcp(operator, auth_recipe),
        oidc=_build_oidc(operator, auth_recipe),
        oauth_storage=OAuthStorageConfig(
            directory=_oauth_storage_directory(operator),
            encryption_key=_purpose_secret(operator.root_secret, "oauth-token-storage"),
        ),
        connector_security=ConnectorSecurityConfig(
            configuration_secret=_purpose_secret(
                operator.root_secret, "connector-configuration"
            ),
            approval_state_key=_purpose_secret(
                operator.root_secret, "connector-approval-state"
            ),
        ),
        connector_store=ConnectorStoreConfig(
            type=operator.connector_store,
            sqlite_path=_sqlite_path(operator),
        ),
        openapi_connectors=OpenApiConnectorConfig(
            json_import_max_bytes=operator.openapi_json_import_max_bytes,
            url_retrieval_timeout_seconds=operator.openapi_url_retrieval_timeout_seconds,
            execution_connect_timeout_seconds=operator.openapi_execution_connect_timeout_seconds,
            execution_read_timeout_seconds=operator.openapi_execution_read_timeout_seconds,
            execution_write_timeout_seconds=operator.openapi_execution_write_timeout_seconds,
            execution_pool_timeout_seconds=operator.openapi_execution_pool_timeout_seconds,
        ),
        cors=CorsConfig(origins=_cors_origins(operator)),
        feature_toggles=FeatureTogglesConfig(
            mcp_administrator_enabled=operator.feature_mcp_administrator_enabled,
        ),
        admin_authentication=_build_admin_auth(operator, auth_recipe),
    )
