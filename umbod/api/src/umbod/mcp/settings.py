from umbod.config import (
    AppConfig,
    EndpointsConfig,
    McpConfig,
    OAuthStorageConfig,
    OidcConfig,
    RuntimeConfig,
    load_app_config,
)

MCPAppSettings = AppConfig
MCPSettings = McpConfig
OIDCSettings = OidcConfig
OIDCOAuthStorageSettings = OAuthStorageConfig
PublicEndpointSettings = EndpointsConfig
RuntimeSettings = RuntimeConfig

__all__ = [
    "MCPAppSettings",
    "MCPSettings",
    "OIDCOAuthStorageSettings",
    "OIDCSettings",
    "PublicEndpointSettings",
    "RuntimeSettings",
    "load_app_config",
]
