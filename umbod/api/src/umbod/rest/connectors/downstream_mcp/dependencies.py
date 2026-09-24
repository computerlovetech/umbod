from umbod.core.connectors.downstream_mcp.adapters.composition import (
    DownstreamMcpConnections,
    create_downstream_mcp_connections,
    create_downstream_mcp_discovery,
)
from umbod.core.connectors.downstream_mcp.adapters.settings import DownstreamMcpInfrastructureSettings

from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores, create_downstream_mcp_stores
from typing import Annotated
from uuid import uuid4
from fastapi import Depends
from umbod.core.identity import AggregateConnectorIdentityCatalog, ConnectorIdentity
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolIdentitySource, PublicToolNameValidator
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.activation import (
    ActivationPort,
    ActivationStore,
    CapabilityActivationService,
    CapabilitySourceActivationCatalog,
    InMemoryActivationNotifier,
)
from umbod.core.connectors.downstream_mcp.activation import DownstreamConnectorActivation
from umbod.core.connectors.downstream_mcp.catalog import DownstreamConnectorCatalogLifecycle, StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.management import DownstreamConnectorCreator, DownstreamConnectorDeleter, DownstreamConnectorPreparation, DownstreamConnectorQueries, DownstreamConnectorUpdater
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStore, ConnectorHealthStore, EncryptedCredentialStore, ToolCatalogStore
from umbod.core.connectors.downstream_mcp.probe import DownstreamMcpProbe
from umbod.core.connectors.downstream_mcp.publishing import DownstreamConnectorPublisher
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions import GroupPermissionStore
from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.rest.connectors.dependencies import (
    get_capability_activation_store,
    get_connector_event_stream,
    get_connector_publishing_store,
)
from umbod.rest.connectors.native.dependencies import get_connector_registry
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.mcp_permissions.dependencies import get_group_permission_store
from messaging.no_op import NoOpEventStream
from messaging.ports import EventStream
Factories = Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]

class UuidDownstreamConnectorIdGenerator:

    def new_id(self) -> str:
        return str(uuid4())

def get_downstream_infrastructure_settings(factories: Factories) -> DownstreamMcpInfrastructureSettings:
    return downstream_mcp_infrastructure_settings_from_app_config(factories.settings)

async def get_downstream_stores(settings: Annotated[DownstreamMcpInfrastructureSettings, Depends(get_downstream_infrastructure_settings)], factories: Factories) -> DownstreamMcpStores:
    await factories.persistence_runtime.readiness.ensure_ready()
    return await create_downstream_mcp_stores(
        settings.credential_secret, factories.persistence_runtime.database
    )

def get_definition_store(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)]) -> ConnectorDefinitionStore:
    return stores.definitions

def get_credential_store(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)]) -> EncryptedCredentialStore:
    return stores.credentials

def get_catalog_store(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)]) -> ToolCatalogStore:
    return stores.catalogs

def get_health_store(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)]) -> ConnectorHealthStore:
    return stores.health

def get_downstream_connections(settings: Annotated[DownstreamMcpInfrastructureSettings, Depends(get_downstream_infrastructure_settings)], stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)]) -> DownstreamMcpConnections:
    return create_downstream_mcp_connections(settings, stores.credentials)

def get_downstream_connector_probe(connections: Annotated[DownstreamMcpConnections, Depends(get_downstream_connections)]) -> DownstreamMcpProbe:
    return connections.connection

def get_downstream_connector_preparation(probe: Annotated[DownstreamMcpProbe, Depends(get_downstream_connector_probe)], settings: Annotated[DownstreamMcpInfrastructureSettings, Depends(get_downstream_infrastructure_settings)]) -> DownstreamConnectorPreparation:
    return DownstreamConnectorPreparation(probe)

def get_downstream_connector_queries(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)], publishing: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)]) -> DownstreamConnectorQueries:
    return DownstreamConnectorQueries(stores.definitions, stores.credentials, stores.catalogs, stores.health, publishing)

def get_public_tool_name_validator() -> PublicToolNameValidator:
    return PublicToolNameValidator()

class RegistryPublicToolIdentitySource:

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry

    async def identities(self) -> tuple[PublicToolIdentity, ...]:
        return tuple((PublicToolIdentity(connector_id=definition.metadata.id, tool_name_prefix=definition.tool_name_prefix, operation_name=operation_name) for definition in self._registry.list_connector_definitions(ConnectorDefinitionFilter(availability='available')) for operation_name in definition.tool_descriptions))

def get_public_tool_identity_source(registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)]) -> PublicToolIdentitySource:
    return RegistryPublicToolIdentitySource(registry)

def get_downstream_connector_updater(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)], publishing: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)], event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)], preparation: Annotated[DownstreamConnectorPreparation, Depends(get_downstream_connector_preparation)], queries: Annotated[DownstreamConnectorQueries, Depends(get_downstream_connector_queries)], validator: Annotated[PublicToolNameValidator, Depends(get_public_tool_name_validator)], identity_source: Annotated[PublicToolIdentitySource, Depends(get_public_tool_identity_source)]) -> DownstreamConnectorUpdater:
    return DownstreamConnectorUpdater(stores.credentials, stores.catalogs, publishing, event_stream or NoOpEventStream(), stores.unit_of_work, preparation, queries, validator, identity_source)

def get_downstream_connector_catalog_lifecycle(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)], probe: Annotated[DownstreamMcpProbe, Depends(get_downstream_connector_probe)], publishing: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)], event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)], queries: Annotated[DownstreamConnectorQueries, Depends(get_downstream_connector_queries)], factories: Factories) -> DownstreamConnectorCatalogLifecycle:
    discovery = create_downstream_mcp_discovery(downstream_mcp_infrastructure_settings_from_app_config(factories.settings), probe)
    return DownstreamConnectorCatalogLifecycle(stores.credentials, stores.catalogs, discovery, publishing, event_stream or NoOpEventStream(), stores.unit_of_work, queries)

def get_downstream_connector_publisher(publishing: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)], event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)], queries: Annotated[DownstreamConnectorQueries, Depends(get_downstream_connector_queries)], validator: Annotated[PublicToolNameValidator, Depends(get_public_tool_name_validator)], identity_source: Annotated[PublicToolIdentitySource, Depends(get_public_tool_identity_source)]) -> DownstreamConnectorPublisher:
    return DownstreamConnectorPublisher(publishing, event_stream or NoOpEventStream(), queries, validator, identity_source)

def get_downstream_connector_deleter(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)], permissions: Annotated[GroupPermissionStore, Depends(get_group_permission_store)], publishing: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)], event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)], queries: Annotated[DownstreamConnectorQueries, Depends(get_downstream_connector_queries)]) -> DownstreamConnectorDeleter:
    return DownstreamConnectorDeleter(permissions, publishing, event_stream or NoOpEventStream(), stores.unit_of_work, queries)

def get_downstream_tool_activation_port(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)], catalogs: Annotated[ToolCatalogStore, Depends(get_catalog_store)], activations: Annotated[ActivationStore, Depends(get_capability_activation_store)]) -> ActivationPort:
    capabilities = StoreBackedDownstreamCapabilityCatalog(stores.definitions, catalogs)
    catalog = CapabilitySourceActivationCatalog(capabilities, activations, 'downstream_mcp')
    return CapabilityActivationService(catalog, activations, InMemoryActivationNotifier())

def get_downstream_connector_activation(activations: Annotated[ActivationStore, Depends(get_capability_activation_store)], activation_port: Annotated[ActivationPort, Depends(get_downstream_tool_activation_port)], event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)], queries: Annotated[DownstreamConnectorQueries, Depends(get_downstream_connector_queries)]) -> DownstreamConnectorActivation:
    return DownstreamConnectorActivation(activations, activation_port, event_stream or NoOpEventStream(), queries)

class RegistryIdentitySource:

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry

    async def identities(self) -> tuple[ConnectorIdentity, ...]:
        return tuple((ConnectorIdentity(connector_id=item.metadata.id, connector_type='built_in') for item in self._registry.list_connector_definitions(ConnectorDefinitionFilter(availability='registered'))))

class OpenApiIdentitySource:

    def __init__(self, store: OpenApiConnectorStore) -> None:
        self._store = store

    async def identities(self) -> tuple[ConnectorIdentity, ...]:
        return tuple((ConnectorIdentity(connector_id=item.connector_id, connector_type='openapi') for item in await self._store.list_connectors()))

class DownstreamIdentitySource:

    def __init__(self, store: ConnectorDefinitionStore) -> None:
        self._store = store

    async def identities(self) -> tuple[ConnectorIdentity, ...]:
        return tuple((ConnectorIdentity(connector_id=item.connector_id, connector_type='downstream_mcp') for item in (await self._store.list()).definitions))

async def get_connector_identity_catalog(registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)], factories: Factories, definitions: Annotated[ConnectorDefinitionStore, Depends(get_definition_store)]) -> AggregateConnectorIdentityCatalog:
    return AggregateConnectorIdentityCatalog((RegistryIdentitySource(registry), OpenApiIdentitySource(await factories.openapi_connector_store.create()), DownstreamIdentitySource(definitions)))

def get_downstream_connector_creator(stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)], identity_catalog: Annotated[AggregateConnectorIdentityCatalog, Depends(get_connector_identity_catalog)], preparation: Annotated[DownstreamConnectorPreparation, Depends(get_downstream_connector_preparation)]) -> DownstreamConnectorCreator:
    return DownstreamConnectorCreator(stores.definitions, UuidDownstreamConnectorIdGenerator(), identity_catalog, preparation, stores.unit_of_work)
