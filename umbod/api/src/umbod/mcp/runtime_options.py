from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.publishing.factories import ConfiguredConnectorPublishingStoreFactory

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from typing import cast
from umbod.core.connectors.native.bootstrap import DefaultConnectorRuntimeFactory
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.runtime import ConnectorRuntime, ConnectorToolMapping
from umbod.core.persistence import PersistenceRuntime
from umbod_sdk.connectors.discovery import load_connector_plugins
from umbod.mcp.settings import MCPAppSettings

@dataclass(frozen=True)
class ConnectorRuntimeOptions:
    connector_runtime: ConnectorRuntime | None = None
    connector_registrations: Sequence[object] | None = None
    connector_configuration_store: ConnectorCurrentConfigurationStore | None = None
    connector_publishing_store: ConnectorPublishingStore | None = None
    connector_tool_mappings: Sequence[ConnectorToolMapping] | None = None

@dataclass(frozen=True)
class ConnectorRuntimeSourceStores:
    connector_configuration_store: ConnectorCurrentConfigurationStore | None = None
    connector_publishing_store: ConnectorPublishingStore | None = None

@dataclass(frozen=True)
class ConnectorStorePair:
    connector_configuration_store: ConnectorCurrentConfigurationStore | None
    connector_publishing_store: ConnectorPublishingStore | None

@dataclass(frozen=True)
class HttpConnectorRuntimeStateSourceStrategy:
    pass

@dataclass(frozen=True)
class StoreBackedConnectorRuntimeStateSourceStrategy:
    pass

@dataclass(frozen=True)
class LocalConnectorRuntimeStateSourceStrategy:
    connector_configuration_store: ConnectorCurrentConfigurationStore
    connector_publishing_store: ConnectorPublishingStore
ConnectorRuntimeStateSourceStrategy = HttpConnectorRuntimeStateSourceStrategy | StoreBackedConnectorRuntimeStateSourceStrategy | LocalConnectorRuntimeStateSourceStrategy

def resolve_connector_runtime_state_source_strategy(source_stores: ConnectorRuntimeSourceStores, configured_strategy: ConnectorRuntimeStateSourceStrategy) -> ConnectorRuntimeStateSourceStrategy:
    configuration_store = source_stores.connector_configuration_store
    publishing_store = source_stores.connector_publishing_store
    if configuration_store is None and publishing_store is None:
        return configured_strategy
    if configuration_store is None or publishing_store is None:
        raise ValueError('connector runtime source stores must provide both configuration and publishing stores')
    return LocalConnectorRuntimeStateSourceStrategy(configuration_store, publishing_store)

async def resolve_connector_runtime(settings: MCPAppSettings, options: ConnectorRuntimeOptions, persistence_runtime: PersistenceRuntime) -> ConnectorRuntime:
    if options.connector_runtime is not None:
        return options.connector_runtime
    if _uses_default_connector_runtime(options):
        await persistence_runtime.readiness.ensure_ready()
        return await DefaultConnectorRuntimeFactory(load_connector_plugins, partial(create_encrypted_connector_configuration_store, persistence_runtime.database), ConfiguredConnectorPublishingStoreFactory(persistence_runtime.database)).create(settings)
    return ConnectorRuntime(connector_registrations=cast(Sequence[object], options.connector_registrations or []), connector_configuration_store=options.connector_configuration_store, connector_publishing_store=options.connector_publishing_store, connector_tool_mappings=cast(Sequence[ConnectorToolMapping], options.connector_tool_mappings or []))

def _uses_default_connector_runtime(options: ConnectorRuntimeOptions) -> bool:
    return options.connector_registrations is None and options.connector_configuration_store is None and (options.connector_publishing_store is None) and (options.connector_tool_mappings is None)
