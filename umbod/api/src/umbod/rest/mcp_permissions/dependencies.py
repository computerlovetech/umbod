from typing import Annotated

from fastapi import Depends

from umbod.core.capabilities import (
    CatalogCapabilityReadiness,
    ConnectorStoreCapabilityActivation,
    ConnectorStoreCapabilityPublication,
)
from umbod.core.connectors.native.capabilities import (
    NativeCapabilityCatalog,
    NativeCapabilityReadiness,
)
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.rest.connectors.dependencies import (
    get_capability_activation_store,
    get_connector_event_stream,
    get_connector_publishing_store,
)
from umbod.rest.connectors.native.dependencies import (
    get_connector_current_configuration_store,
    get_connector_registry,
)
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.mcp_permissions.events import McpPermissionEventPublisher
from umbod.core.connectors.downstream_mcp.catalog import (
    StoreBackedDownstreamCapabilityCatalog,
)
from umbod.core.permissions import (
    AdminGroupPermissionManagement,
    AssignablePermissionCatalog,
    CapabilityPermissionCatalog,
    CompositeConnectorToolPermissionCatalog,
    GroupPermissionManagementService,
    GroupPermissionStore,
    NoopPermissionChangeNotifier,
)
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import (
    ConnectorDefinitionFilter,
    ConnectorRegistry,
)
from umbod.core.activation import ActivationStore
from messaging.no_op import NoOpEventStream
from messaging.ports import EventStream


async def get_group_permission_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> GroupPermissionStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return await dependency_factories.group_permission_store.create()


def get_native_permission_catalog(
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    configuration_store: Annotated[
        ConnectorCurrentConfigurationStore,
        Depends(get_connector_current_configuration_store),
    ],
    publishing_store: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)],
    activation_store: Annotated[
        ActivationStore, Depends(get_capability_activation_store)
    ],
) -> AssignablePermissionCatalog:
    capabilities = NativeCapabilityCatalog.from_registry(connector_registry)
    schemas = {
        definition.metadata.id: definition.configuration_schema
        for definition in connector_registry.list_connector_definitions(
            ConnectorDefinitionFilter(availability="registered")
        )
    }
    return CapabilityPermissionCatalog(
        capabilities,
        "native",
        ConnectorStoreCapabilityPublication("native", publishing_store),
        ConnectorStoreCapabilityActivation("native", activation_store),
        NativeCapabilityReadiness(schemas, configuration_store),
        validate_connector_availability=True,
        validate_tool_availability=True,
        include_connector_without_tools=True,
    )


async def get_connector_permission_catalog(
    native_catalog: Annotated[AssignablePermissionCatalog, Depends(get_native_permission_catalog)],
    publishing_store: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)],
    activation_store: Annotated[
        ActivationStore, Depends(get_capability_activation_store)
    ],
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories,
        Depends(get_connector_api_dependency_factories),
    ],
) -> AssignablePermissionCatalog:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    openapi_catalog = await _openapi_permission_catalog(
        dependency_factories, publishing_store, activation_store
    )
    downstream_catalog = _downstream_permission_catalog(
        dependency_factories, publishing_store, activation_store
    )
    return CompositeConnectorToolPermissionCatalog(
        (native_catalog, openapi_catalog, downstream_catalog)
    )


async def _openapi_permission_catalog(
    factories: ConnectorApiDependencyFactories,
    publishing: ConnectorPublishingStore,
    activations: ActivationStore,
) -> AssignablePermissionCatalog:
    capabilities = StoreBackedOpenApiCapabilityCatalog(
        await factories.openapi_connector_store.create()
    )
    return CapabilityPermissionCatalog(
        capabilities,
        "openapi",
        ConnectorStoreCapabilityPublication("openapi", publishing),
        ConnectorStoreCapabilityActivation("openapi", activations),
        CatalogCapabilityReadiness(capabilities),
        validate_connector_availability=False,
        validate_tool_availability=False,
        include_connector_without_tools=False,
    )


def _downstream_permission_catalog(
    factories: ConnectorApiDependencyFactories,
    publishing: ConnectorPublishingStore,
    activations: ActivationStore,
) -> AssignablePermissionCatalog:
    capabilities = StoreBackedDownstreamCapabilityCatalog(
        factories.downstream_mcp_definition_store.create(),
        factories.downstream_mcp_catalog_store.create(),
    )
    return CapabilityPermissionCatalog(
        capabilities,
        "downstream_mcp",
        ConnectorStoreCapabilityPublication("downstream_mcp", publishing),
        ConnectorStoreCapabilityActivation("downstream_mcp", activations),
        CatalogCapabilityReadiness(capabilities),
        validate_connector_availability=False,
        validate_tool_availability=False,
        include_connector_without_tools=False,
    )


def get_admin_group_permission_management(
    store: Annotated[GroupPermissionStore, Depends(get_group_permission_store)],
    catalog: Annotated[AssignablePermissionCatalog, Depends(get_connector_permission_catalog)],
) -> AdminGroupPermissionManagement:
    return GroupPermissionManagementService(
        store=store,
        catalog=catalog,
        notifier=NoopPermissionChangeNotifier(),
    )


def get_mcp_permission_event_publisher(
    event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)],
) -> McpPermissionEventPublisher:
    return McpPermissionEventPublisher(event_stream or NoOpEventStream())
