from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.publishing.factories import ConfiguredConnectorPublishingStoreFactory

from collections.abc import Mapping
from functools import partial
from typing import Any
from pydantic import Field
from umbod.mcp.proxies import Model
from umbod.config import load_app_config
from umbod.core.connectors.native.bootstrap import DefaultConnectorRuntimeFactory
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.persistence import PersistenceRuntime
from umbod_sdk.connectors.discovery import load_connector_plugins
from umbod.mcp.settings import MCPAppSettings

class DefaultMcpConnectorRuntimeConfig(Model):
    settings: MCPAppSettings = Field(default_factory=load_app_config)

async def create_default_mcp_connector_runtime(config_data: DefaultMcpConnectorRuntimeConfig | MCPAppSettings | Mapping[str, Any], persistence_runtime: PersistenceRuntime) -> ConnectorRuntime:
    config = _default_mcp_connector_runtime_config(config_data)
    await persistence_runtime.readiness.ensure_ready()
    return await DefaultConnectorRuntimeFactory(load_connector_plugins, partial(create_encrypted_connector_configuration_store, persistence_runtime.database), ConfiguredConnectorPublishingStoreFactory(persistence_runtime.database)).create(config.settings)

async def create_default_mcp_connector_runtime_from_environment(persistence_runtime: PersistenceRuntime) -> ConnectorRuntime:
    settings = DefaultMcpConnectorRuntimeConfig().settings
    await persistence_runtime.readiness.ensure_ready()
    return await DefaultConnectorRuntimeFactory(load_connector_plugins, partial(create_encrypted_connector_configuration_store, persistence_runtime.database), ConfiguredConnectorPublishingStoreFactory(persistence_runtime.database)).create(settings)

def _default_mcp_connector_runtime_config(config_data: DefaultMcpConnectorRuntimeConfig | MCPAppSettings | Mapping[str, Any]) -> DefaultMcpConnectorRuntimeConfig:
    if isinstance(config_data, DefaultMcpConnectorRuntimeConfig):
        return config_data
    if isinstance(config_data, MCPAppSettings):
        return DefaultMcpConnectorRuntimeConfig(settings=config_data)
    return DefaultMcpConnectorRuntimeConfig.model_validate(config_data)
__all__ = ['DefaultMcpConnectorRuntimeConfig', 'create_default_mcp_connector_runtime', 'create_default_mcp_connector_runtime_from_environment']
