from typing import Annotated, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from umbod.config import defaults

Profile = str
AuthRecipe = str


def _parse_comma_separated_values(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class OperatorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UMBOD_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    profile: str = "local"
    auth: Optional[str] = None

    app_name: str = defaults.APP_NAME
    log_level: str = defaults.LOG_LEVEL

    public_site_origin: str = Field(
        default=defaults.PUBLIC_SITE_ORIGIN,
        validation_alias="UMBOD_PUBLIC_SITE_ORIGIN",
    )
    public_api_origin: str = Field(
        default=defaults.PUBLIC_API_ORIGIN,
        validation_alias="UMBOD_PUBLIC_API_ORIGIN",
    )
    public_mcp_origin: str = Field(
        default=defaults.PUBLIC_MCP_ORIGIN,
        validation_alias="UMBOD_PUBLIC_MCP_ORIGIN",
    )
    internal_api_origin: str = Field(
        default=defaults.INTERNAL_API_ORIGIN,
        validation_alias="UMBOD_INTERNAL_API_ORIGIN",
    )

    data_dir: str = defaults.DATA_DIR
    connector_store: str = Field(
        default="inmemory",
        validation_alias="UMBOD_CONNECTOR_STORE",
    )
    connector_store_sqlite_path: Optional[str] = Field(
        default=None,
        validation_alias="UMBOD_CONNECTOR_STORE_SQLITE_PATH",
    )
    root_secret: str = Field(
        default="",
        validation_alias="UMBOD_ROOT_SECRET",
    )
    openapi_json_import_max_bytes: int = Field(
        default=defaults.OPENAPI_JSON_IMPORT_MAX_BYTES,
        gt=0,
    )
    openapi_url_retrieval_timeout_seconds: float = Field(
        default=defaults.OPENAPI_URL_RETRIEVAL_TIMEOUT_SECONDS, gt=0
    )
    openapi_execution_connect_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_CONNECT_TIMEOUT_SECONDS, gt=0
    )
    openapi_execution_read_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_READ_TIMEOUT_SECONDS, gt=0
    )
    openapi_execution_write_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_WRITE_TIMEOUT_SECONDS, gt=0
    )
    openapi_execution_pool_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_POOL_TIMEOUT_SECONDS, gt=0
    )
    cors_origins: Annotated[Optional[list[str]], NoDecode] = Field(
        default=None,
        validation_alias="UMBOD_CORS_ORIGINS",
    )

    oidc_domain: str = ""
    oidc_tenant_id: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_audience: str = ""
    oidc_config_url: str = ""
    oidc_issuer_url: str = ""
    oidc_required_scopes: Annotated[list[str], NoDecode] = Field(default_factory=list)
    oauth_storage_directory: Optional[str] = Field(
        default=None,
        validation_alias="UMBOD_OAUTH_STORAGE_DIRECTORY",
    )
    admin_group: str = Field(
        default=defaults.ADMIN_REQUIRED_MEMBERSHIP,
        validation_alias="UMBOD_ADMIN_GROUP",
    )
    admin_membership_claim: Optional[str] = Field(
        default=None,
        validation_alias="UMBOD_ADMIN_MEMBERSHIP_CLAIM",
    )
    mcp_permission_claim: Optional[str] = Field(
        default=None,
        validation_alias="UMBOD_MCP_PERMISSION_CLAIM",
    )
    admin_jwks_url: str = Field(
        default="",
        validation_alias="UMBOD_ADMIN_JWKS_URL",
    )

    rest_port: int = Field(
        default=defaults.REST_PORT,
        gt=0,
        validation_alias="UMBOD_REST_PORT",
    )
    rest_metrics_port: int = Field(
        default=defaults.REST_METRICS_PORT,
        gt=0,
        validation_alias="UMBOD_REST_METRICS_PORT",
    )
    mcp_port: int = Field(
        default=defaults.MCP_PORT, validation_alias="UMBOD_MCP_PORT"
    )
    mcp_metrics_port: int = Field(
        default=defaults.MCP_METRICS_PORT,
        gt=0,
        validation_alias="UMBOD_MCP_METRICS_PORT",
    )
    mcp_messaging_transport: Literal["http", "sql"] = Field(
        default="http",
        validation_alias="UMBOD_MCP_MESSAGING_TRANSPORT",
    )
    mcp_tool_exposure: str = Field(
        default=defaults.MCP_TOOL_EXPOSURE_MODE,
        validation_alias="UMBOD_MCP_TOOL_EXPOSURE",
    )
    mcp_code_execution_timeout_seconds: float = Field(
        default=defaults.MCP_CODE_EXECUTION_TIMEOUT_SECONDS,
        validation_alias="UMBOD_MCP_CODE_EXECUTION_TIMEOUT_SECONDS",
    )
    mcp_maximum_uploaded_file_bytes: int = Field(
        default=defaults.MCP_MAXIMUM_UPLOADED_FILE_BYTES,
        gt=0,
        validation_alias="UMBOD_MCP_MAXIMUM_UPLOADED_FILE_BYTES",
    )
    mcp_downstream_oauth_enabled: bool = Field(
        default=False,
        validation_alias="UMBOD_MCP_DOWNSTREAM_OAUTH_ENABLED",
        description="Allow stored per-connection OAuth credentials for downstream MCP servers.",
    )
    mcp_downstream_discovery_enabled: bool = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_ENABLED,
        validation_alias="UMBOD_MCP_DOWNSTREAM_DISCOVERY_ENABLED",
    )
    mcp_downstream_discovery_timeout_seconds: float = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS,
        validation_alias="UMBOD_MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS",
    )
    mcp_downstream_refresh_interval_seconds: float = Field(
        default=defaults.MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS,
        validation_alias="UMBOD_MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS",
    )
    mcp_downstream_discovery_concurrency: int = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY,
        validation_alias="UMBOD_MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY",
    )
    mcp_downstream_discovery_jitter_ratio: float = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO,
        validation_alias="UMBOD_MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO",
    )
    mcp_downstream_discovery_maximum_backoff_seconds: float = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS,
        validation_alias="UMBOD_MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS",
    )
    mcp_stateless_http: bool = Field(
        default=False,
        validation_alias="UMBOD_MCP_STATELESS_HTTP",
    )
    mcp_auth_debug_enabled: bool = Field(
        default=False,
        validation_alias="UMBOD_MCP_AUTH_DEBUG_ENABLED",
    )
    mcp_test_user_email: str = Field(
        default=defaults.MCP_TEST_USER_EMAIL,
        validation_alias="UMBOD_MCP_TEST_USER_EMAIL",
    )
    mcp_test_bearer_token: str = Field(
        default=defaults.MCP_TEST_BEARER_TOKEN,
        validation_alias="UMBOD_MCP_TEST_BEARER_TOKEN",
    )
    mcp_test_user_group: str = Field(
        default=defaults.MCP_TEST_USER_GROUP,
        validation_alias="UMBOD_MCP_TEST_USER_GROUP",
    )
    feature_mcp_administrator_enabled: bool = Field(
        default=True,
        validation_alias="UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED",
    )

    admin_jwt_header_name: str = Field(
        default=defaults.ADMIN_JWT_HEADER_NAME,
        validation_alias="UMBOD_ADMIN_JWT_HEADER",
    )
    admin_debug_enabled: bool = Field(
        default=False,
        validation_alias="UMBOD_ADMIN_AUTHENTICATION_DEBUG_ENABLED",
    )
    admin_simulated_admin: bool = Field(
        default=True,
        validation_alias="UMBOD_ADMIN_AUTHENTICATION_SIMULATED_ADMIN",
    )
    admin_simulated_user_id: str = Field(
        default=defaults.ADMIN_SIMULATED_USER_ID,
        validation_alias="UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_ID",
    )
    admin_simulated_user_email: str = Field(
        default=defaults.ADMIN_SIMULATED_USER_EMAIL,
        validation_alias="UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_EMAIL",
    )
    admin_simulated_user_name: str = Field(
        default=defaults.ADMIN_SIMULATED_USER_NAME,
        validation_alias="UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_NAME",
    )

    @field_validator("oidc_required_scopes", mode="before")
    @classmethod
    def _parse_required_scopes(cls, value: str | list[str]) -> list[str]:
        return _parse_comma_separated_values(value)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        return _parse_comma_separated_values(value)
