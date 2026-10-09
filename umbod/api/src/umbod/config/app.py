import re
from typing import Annotated, Literal, Union
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from umbod.config import defaults


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RuntimeConfig(ConfigModel):
    app_name: str = defaults.APP_NAME
    log_level: str = defaults.LOG_LEVEL
    profile: str = "local"
    auth: str = "dev"


class EndpointsConfig(ConfigModel):
    site_base_url: str = defaults.PUBLIC_SITE_ORIGIN
    api_base_url: str = defaults.PUBLIC_API_ORIGIN
    private_api_base_url: str = defaults.INTERNAL_API_ORIGIN
    mcp_base_url: str = defaults.PUBLIC_MCP_ORIGIN

    @field_validator("api_base_url")
    @classmethod
    def validate_public_api_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("public API origin must use HTTPS")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "public API origin must not contain credentials, query, or fragment"
            )
        if parsed.path not in ("", "/"):
            raise ValueError("public API origin must not contain a path")
        return value.rstrip("/")


class RestConfig(ConfigModel):
    port: int = Field(default=defaults.REST_PORT, gt=0)
    metrics_port: int = Field(default=defaults.REST_METRICS_PORT, gt=0)


class OtlpReceiverConfig(ConfigModel):
    enabled: bool = False
    bearer_token: str = Field(default="", repr=False)
    allow_unauthenticated: bool = False
    max_request_bytes: int = Field(default=defaults.OTLP_MAX_REQUEST_BYTES, gt=0)


class McpConfig(ConfigModel):
    port: int = defaults.MCP_PORT
    messaging_transport: Literal["http", "sql"] = "http"
    metrics_port: int = Field(default=defaults.MCP_METRICS_PORT, gt=0)
    connector_tool_exposure_mode: Literal["flat", "gateway", "codemode"] = (
        defaults.MCP_TOOL_EXPOSURE_MODE
    )
    connector_code_execution_timeout_seconds: float = Field(
        default=defaults.MCP_CODE_EXECUTION_TIMEOUT_SECONDS,
        gt=0,
    )
    maximum_uploaded_file_bytes: int = Field(
        default=defaults.MCP_MAXIMUM_UPLOADED_FILE_BYTES,
        gt=0,
    )
    downstream_oauth_enabled: bool = False
    downstream_discovery_enabled: bool = defaults.MCP_DOWNSTREAM_DISCOVERY_ENABLED
    downstream_discovery_timeout_seconds: float = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS, gt=0
    )
    downstream_refresh_interval_seconds: float = Field(
        default=defaults.MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS, gt=0
    )
    downstream_discovery_concurrency: int = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY, gt=0
    )
    downstream_discovery_jitter_ratio: float = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO, ge=0, le=1
    )
    downstream_discovery_maximum_backoff_seconds: float = Field(
        default=defaults.MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS, gt=0
    )
    auth_mode: Literal["none", "oidc", "single_test_user"] = "single_test_user"
    test_user_email: str = defaults.MCP_TEST_USER_EMAIL
    test_bearer_token: str = defaults.MCP_TEST_BEARER_TOKEN
    test_user_group: str = defaults.MCP_TEST_USER_GROUP
    permission_group_claim: str = defaults.PERMISSION_GROUP_CLAIM
    auth_debug_enabled: bool = False
    stateless_http: bool = False


class OidcConfig(ConfigModel):
    provider: Literal["google", "azure_entra_id", "auth0"] = "google"
    config_url: str = ""
    issuer_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    audience: str = ""
    tenant_id: str = ""
    required_scopes: list[str] = Field(default_factory=list)
    jwt_signing_key: str = ""


class OAuthStorageConfig(ConfigModel):
    directory: str = defaults.OAUTH_STORAGE_DIRECTORY
    encryption_key: str = ""


class ConnectorSecurityConfig(ConfigModel):
    configuration_secret: str = ""
    approval_state_key: str = ""


class ConnectorStoreConfig(ConfigModel):
    type: Literal["inmemory", "sqlite"] = "inmemory"
    sqlite_path: str = defaults.CONNECTOR_STORE_SQLITE_PATH


class InMemoryConnectorStoreConfig(ConnectorStoreConfig):
    type: Literal["inmemory"] = "inmemory"


class SQLiteConnectorStoreConfig(ConnectorStoreConfig):
    type: Literal["sqlite"] = "sqlite"


PersistenceConfig = Annotated[
    Union[InMemoryConnectorStoreConfig, SQLiteConnectorStoreConfig],
    Field(discriminator="type"),
]


class OpenApiConnectorConfig(ConfigModel):
    json_import_max_bytes: int = Field(
        default=defaults.OPENAPI_JSON_IMPORT_MAX_BYTES, gt=0
    )
    url_retrieval_timeout_seconds: float = Field(
        default=defaults.OPENAPI_URL_RETRIEVAL_TIMEOUT_SECONDS, gt=0
    )
    execution_connect_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_CONNECT_TIMEOUT_SECONDS, gt=0
    )
    execution_read_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_READ_TIMEOUT_SECONDS, gt=0
    )
    execution_write_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_WRITE_TIMEOUT_SECONDS, gt=0
    )
    execution_pool_timeout_seconds: float = Field(
        default=defaults.OPENAPI_EXECUTION_POOL_TIMEOUT_SECONDS, gt=0
    )


class CorsConfig(ConfigModel):
    origins: list[str] = Field(default_factory=lambda: [defaults.PUBLIC_SITE_ORIGIN])


class FeatureTogglesConfig(ConfigModel):
    mcp_administrator_enabled: bool = True


class AdminAuthConfig(ConfigModel):
    environment: Literal["development", "production"] = "development"
    mode: Literal["disabled", "jwt", "simulation"] = "simulation"
    jwt_header_name: str = defaults.ADMIN_JWT_HEADER_NAME
    jwks_url: str = ""
    membership_claim: str = defaults.PERMISSION_GROUP_CLAIM
    required_membership: str = defaults.ADMIN_REQUIRED_MEMBERSHIP
    simulated_admin: bool = True
    simulated_user_id: str = defaults.ADMIN_SIMULATED_USER_ID
    simulated_user_email: str = defaults.ADMIN_SIMULATED_USER_EMAIL
    simulated_user_name: str = defaults.ADMIN_SIMULATED_USER_NAME
    debug_enabled: bool = False


class UserProfileConfig(ConfigModel):
    mode: Literal["access_claims", "id_token"] = "access_claims"
    jwt_header_name: str = "X-Auth-Request-ID-Token"
    name_claim: str = "name"
    email_claim: str = "email"
    picture_claim: str = "picture"

    @field_validator("jwt_header_name")
    @classmethod
    def validate_header(cls, value: str) -> str:
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", value):
            raise ValueError("User profile JWT header must be an HTTP header name")
        if value.lower() == "authorization":
            raise ValueError("User profile JWT header cannot be Authorization")
        return value

    @field_validator("name_claim", "email_claim", "picture_claim")
    @classmethod
    def validate_mapping(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("User profile claim mappings must not be blank")
        return value


class AppConfig(ConfigModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    endpoints: EndpointsConfig = Field(default_factory=EndpointsConfig)
    rest: RestConfig = Field(default_factory=RestConfig)
    otlp_receiver: OtlpReceiverConfig = Field(default_factory=OtlpReceiverConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    oidc: OidcConfig = Field(default_factory=OidcConfig)
    oauth_storage: OAuthStorageConfig = Field(default_factory=OAuthStorageConfig)
    connector_security: ConnectorSecurityConfig = Field(
        default_factory=ConnectorSecurityConfig
    )
    connector_store: PersistenceConfig = Field(
        default_factory=InMemoryConnectorStoreConfig
    )
    openapi_connectors: OpenApiConnectorConfig = Field(
        default_factory=OpenApiConnectorConfig
    )
    cors: CorsConfig = Field(default_factory=CorsConfig)
    feature_toggles: FeatureTogglesConfig = Field(default_factory=FeatureTogglesConfig)
    admin_authentication: AdminAuthConfig = Field(default_factory=AdminAuthConfig)
    user_profile: UserProfileConfig = Field(default_factory=UserProfileConfig)

    @model_validator(mode="after")
    def validate_user_profile(self) -> "AppConfig":
        if (
            self.user_profile.jwt_header_name.lower()
            == self.admin_authentication.jwt_header_name.lower()
        ):
            raise ValueError("User profile and access JWT headers must be distinct")
        if self.user_profile.mode == "id_token":
            if (
                self.admin_authentication.mode != "jwt"
                or self.admin_authentication.environment != "production"
            ):
                raise ValueError(
                    "ID-token profiles require real production JWT authentication"
                )
            if not all(
                value.strip()
                for value in (
                    self.oidc.issuer_url,
                    self.oidc.client_id,
                    self.admin_authentication.jwks_url,
                )
            ):
                raise ValueError(
                    "ID-token profiles require OIDC issuer, client ID and admin JWKS URL"
                )
        return self

    @field_validator("connector_store", mode="before")
    @classmethod
    def normalize_connector_store_config(cls, value: object) -> object:
        if type(value) is ConnectorStoreConfig:
            return value.model_dump()
        return value
