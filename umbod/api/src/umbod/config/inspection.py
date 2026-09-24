from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, Union

from pydantic import BaseModel, ConfigDict

from umbod.config.app import AppConfig

ConfigurationValue = Union[str, int, float, bool, list[str]]
ConfigurationValueType = Literal["string", "integer", "number", "boolean", "string_list"]


class ConfigurationEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    variable: str
    label: str
    description: str
    type: ConfigurationValueType
    value: ConfigurationValue


class ConfigurationGroup(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    entries: list[ConfigurationEntry]


class InstanceConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    groups: list[ConfigurationGroup]


class InstanceConfigurationInspector(Protocol):
    def inspect(self) -> Sequence[ConfigurationGroup]: ...


@dataclass(frozen=True)
class ConfigurationCatalogEntry:
    group_id: str
    group_label: str
    section: str
    field: str
    variable: str
    label: str
    description: str
    value_type: ConfigurationValueType

    def read(self, config: AppConfig) -> ConfigurationValue:
        return getattr(getattr(config, self.section), self.field)


_SECRET_FIELDS: tuple[tuple[str, str], ...] = (
    ("connector_security", "configuration_secret"),
    ("connector_security", "approval_state_key"),
    ("oidc", "client_secret"),
    ("oidc", "jwt_signing_key"),
    ("oauth_storage", "encryption_key"),
    ("mcp", "test_bearer_token"),
)

_CATALOG: tuple[ConfigurationCatalogEntry, ...] = (
    ConfigurationCatalogEntry(
        "runtime",
        "Runtime",
        "runtime",
        "app_name",
        "UMBOD_APP_NAME",
        "Application name",
        "Name used to identify this Umbod instance.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "runtime",
        "Runtime",
        "runtime",
        "log_level",
        "UMBOD_LOG_LEVEL",
        "Log level",
        "Minimum severity emitted by application logging.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "endpoints",
        "Endpoints",
        "endpoints",
        "site_base_url",
        "UMBOD_PUBLIC_SITE_ORIGIN",
        "Public site origin",
        "Public origin used for the Umbod web interface.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "endpoints",
        "Endpoints",
        "endpoints",
        "api_base_url",
        "UMBOD_PUBLIC_API_ORIGIN",
        "Public API origin",
        "Public origin used to reach the REST API.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "endpoints",
        "Endpoints",
        "endpoints",
        "mcp_base_url",
        "UMBOD_PUBLIC_MCP_ORIGIN",
        "Public MCP origin",
        "Public origin used to reach the MCP service.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "features",
        "Features",
        "feature_toggles",
        "mcp_administrator_enabled",
        "UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED",
        "MCP administrator enabled",
        "Whether MCP administrator tools are available.",
        "boolean",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "connector_tool_exposure_mode",
        "UMBOD_MCP_TOOL_EXPOSURE",
        "Tool exposure mode",
        "How connector tools are exposed through MCP.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "connector_code_execution_timeout_seconds",
        "UMBOD_MCP_CODE_EXECUTION_TIMEOUT_SECONDS",
        "Code execution timeout",
        "Maximum connector code execution time in seconds.",
        "number",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "maximum_uploaded_file_bytes",
        "UMBOD_MCP_MAXIMUM_UPLOADED_FILE_BYTES",
        "Maximum uploaded file size",
        "Maximum connector file input size in bytes.",
        "integer",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "downstream_discovery_enabled",
        "UMBOD_MCP_DOWNSTREAM_DISCOVERY_ENABLED",
        "Downstream discovery enabled",
        "Whether downstream MCP discovery is enabled.",
        "boolean",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "downstream_discovery_timeout_seconds",
        "UMBOD_MCP_DOWNSTREAM_DISCOVERY_TIMEOUT_SECONDS",
        "Discovery timeout",
        "Maximum downstream discovery time in seconds.",
        "number",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "downstream_refresh_interval_seconds",
        "UMBOD_MCP_DOWNSTREAM_REFRESH_INTERVAL_SECONDS",
        "Refresh interval",
        "Interval between downstream refreshes in seconds.",
        "number",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "downstream_discovery_concurrency",
        "UMBOD_MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY",
        "Discovery concurrency",
        "Maximum concurrent downstream discovery operations.",
        "integer",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "downstream_discovery_jitter_ratio",
        "UMBOD_MCP_DOWNSTREAM_DISCOVERY_JITTER_RATIO",
        "Discovery jitter ratio",
        "Jitter applied to downstream discovery scheduling.",
        "number",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "downstream_discovery_maximum_backoff_seconds",
        "UMBOD_MCP_DOWNSTREAM_DISCOVERY_MAXIMUM_BACKOFF_SECONDS",
        "Maximum discovery backoff",
        "Maximum downstream discovery backoff in seconds.",
        "number",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "permission_group_claim",
        "UMBOD_MCP_PERMISSION_CLAIM",
        "Permission group claim",
        "Token claim containing MCP permission groups.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "auth_debug_enabled",
        "UMBOD_MCP_AUTH_DEBUG_ENABLED",
        "Authentication debug enabled",
        "Whether MCP authentication debug behavior is enabled.",
        "boolean",
    ),
    ConfigurationCatalogEntry(
        "mcp",
        "MCP",
        "mcp",
        "stateless_http",
        "UMBOD_MCP_STATELESS_HTTP",
        "Stateless HTTP",
        "Whether MCP HTTP transport operates without session state.",
        "boolean",
    ),
    ConfigurationCatalogEntry(
        "identity",
        "Identity provider",
        "runtime",
        "auth",
        "UMBOD_AUTH",
        "Authentication recipe",
        "Configured authentication recipe.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "identity",
        "Identity provider",
        "oidc",
        "config_url",
        "UMBOD_OIDC_CONFIG_URL",
        "Configuration URL",
        "OpenID Connect discovery configuration URL.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "identity",
        "Identity provider",
        "oidc",
        "issuer_url",
        "UMBOD_OIDC_ISSUER_URL",
        "Issuer URL",
        "Expected OpenID Connect token issuer.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "identity",
        "Identity provider",
        "oidc",
        "client_id",
        "UMBOD_OIDC_CLIENT_ID",
        "Client ID",
        "Public OpenID Connect client identifier.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "identity",
        "Identity provider",
        "oidc",
        "audience",
        "UMBOD_OIDC_AUDIENCE",
        "Audience",
        "Expected OpenID Connect token audience.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "identity",
        "Identity provider",
        "oidc",
        "tenant_id",
        "UMBOD_OIDC_TENANT_ID",
        "Tenant ID",
        "Identity-provider tenant identifier.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "identity",
        "Identity provider",
        "oidc",
        "required_scopes",
        "UMBOD_OIDC_REQUIRED_SCOPES",
        "Required scopes",
        "OpenID Connect scopes required by the instance.",
        "string_list",
    ),
    ConfigurationCatalogEntry(
        "storage",
        "Storage",
        "connector_store",
        "type",
        "UMBOD_CONNECTOR_STORE",
        "Connector store",
        "Persistence implementation used for connector data.",
        "string",
    ),
    ConfigurationCatalogEntry(
        "openapi",
        "OpenAPI connectors",
        "openapi_connectors",
        "json_import_max_bytes",
        "UMBOD_OPENAPI_JSON_IMPORT_MAX_BYTES",
        "Maximum import size",
        "Maximum accepted OpenAPI JSON import size in bytes.",
        "integer",
    ),
    *tuple(
        ConfigurationCatalogEntry(
            "openapi",
            "OpenAPI connectors",
            "openapi_connectors",
            field,
            f"UMBOD_OPENAPI_{variable}",
            label,
            description,
            "number",
        )
        for field, variable, label, description in (
            (
                "url_retrieval_timeout_seconds",
                "URL_RETRIEVAL_TIMEOUT_SECONDS",
                "URL retrieval timeout",
                "Maximum OpenAPI URL retrieval time in seconds.",
            ),
            (
                "execution_connect_timeout_seconds",
                "EXECUTION_CONNECT_TIMEOUT_SECONDS",
                "Connect timeout",
                "OpenAPI execution connection timeout in seconds.",
            ),
            (
                "execution_read_timeout_seconds",
                "EXECUTION_READ_TIMEOUT_SECONDS",
                "Read timeout",
                "OpenAPI execution read timeout in seconds.",
            ),
            (
                "execution_write_timeout_seconds",
                "EXECUTION_WRITE_TIMEOUT_SECONDS",
                "Write timeout",
                "OpenAPI execution write timeout in seconds.",
            ),
            (
                "execution_pool_timeout_seconds",
                "EXECUTION_POOL_TIMEOUT_SECONDS",
                "Pool timeout",
                "OpenAPI execution pool timeout in seconds.",
            ),
        )
    ),
    ConfigurationCatalogEntry(
        "security",
        "Security posture",
        "cors",
        "origins",
        "UMBOD_CORS_ORIGINS",
        "CORS origins",
        "Origins allowed to make cross-origin requests.",
        "string_list",
    ),
    ConfigurationCatalogEntry(
        "security",
        "Security posture",
        "runtime",
        "profile",
        "UMBOD_PROFILE",
        "Deployment profile",
        "Configured deployment profile.",
        "string",
    ),
    *tuple(
        ConfigurationCatalogEntry(
            "security",
            "Security posture",
            "admin_authentication",
            field,
            variable,
            label,
            description,
            value_type,
        )
        for field, variable, label, description, value_type in (
            (
                "jwt_header_name",
                "UMBOD_ADMIN_JWT_HEADER",
                "JWT header",
                "Request header carrying administrator authentication.",
                "string",
            ),
            (
                "jwks_url",
                "UMBOD_ADMIN_JWKS_URL",
                "JWKS URL",
                "URL used to retrieve token verification keys.",
                "string",
            ),
            (
                "membership_claim",
                "UMBOD_ADMIN_MEMBERSHIP_CLAIM",
                "Membership claim",
                "Token claim containing administrator memberships.",
                "string",
            ),
            (
                "required_membership",
                "UMBOD_ADMIN_GROUP",
                "Required membership",
                "Membership required to access administration.",
                "string",
            ),
            (
                "debug_enabled",
                "UMBOD_ADMIN_AUTHENTICATION_DEBUG_ENABLED",
                "Authentication debug enabled",
                "Whether administrator authentication debugging is enabled.",
                "boolean",
            ),
        )
    ),
)


class AppConfigInspector:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def inspect(self) -> Sequence[ConfigurationGroup]:
        groups: list[ConfigurationGroup] = []
        for catalog_entry in _CATALOG:
            if not groups or groups[-1].id != catalog_entry.group_id:
                groups.append(
                    ConfigurationGroup(
                        id=catalog_entry.group_id, label=catalog_entry.group_label, entries=[]
                    )
                )
            groups[-1].entries.append(
                ConfigurationEntry(
                    variable=catalog_entry.variable,
                    label=catalog_entry.label,
                    description=catalog_entry.description,
                    type=catalog_entry.value_type,
                    value=catalog_entry.read(self._config),
                )
            )
        return groups


def inspect_app_config(config: AppConfig) -> InstanceConfiguration:
    return InstanceConfiguration(groups=list(AppConfigInspector(config).inspect()))


def safe_app_config_dump(config: AppConfig) -> dict[str, dict[str, ConfigurationValue]]:
    result: dict[str, dict[str, ConfigurationValue]] = config.model_dump()
    for section, field in _SECRET_FIELDS:
        result[section].pop(field, None)
    return result
