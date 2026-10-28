from dataclasses import dataclass

from umbod.core.connectors.downstream_mcp.adapters.composition import create_downstream_mcp_client_factory
from umbod.core.connectors.downstream_mcp.adapters.settings import downstream_mcp_infrastructure_settings_from_app_config
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.connectors.openapi.execution import OutboundHttpClientFactory
from umbod.core.persistence import Database
from umbod.mcp.connectors.downstream_mcp.ports import DownstreamClientFactory
from umbod.mcp.connectors.openapi import OutboundHttpClientFactoryPort
from umbod.mcp.settings import MCPAppSettings


@dataclass(frozen=True)
class OpenApiRuntimeAdapters:
    outbound_http_client_factory: OutboundHttpClientFactoryPort


def create_configured_openapi_runtime_adapters(settings: MCPAppSettings) -> OpenApiRuntimeAdapters:
    openapi_config = settings.openapi_connectors
    return OpenApiRuntimeAdapters(outbound_http_client_factory=OutboundHttpClientFactory(connect_timeout_seconds=openapi_config.execution_connect_timeout_seconds, read_timeout_seconds=openapi_config.execution_read_timeout_seconds, write_timeout_seconds=openapi_config.execution_write_timeout_seconds, pool_timeout_seconds=openapi_config.execution_pool_timeout_seconds))


async def create_configured_downstream_client_factory(settings: MCPAppSettings, database: Database) -> DownstreamClientFactory:
    infrastructure_settings = downstream_mcp_infrastructure_settings_from_app_config(settings)
    stores = await create_downstream_mcp_stores(infrastructure_settings.credential_secret, database)
    return create_downstream_mcp_client_factory(infrastructure_settings, stores.credentials)
