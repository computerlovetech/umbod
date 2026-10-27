from typing import Annotated

from fastapi import Depends

from umbod.core.activation import ActivationStore
from umbod.core.activation.domain import CapabilityActivationReader
from umbod.core.capabilities import (
    CapabilityCatalog,
    CatalogCapabilityReadiness,
    ConnectorStoreCapabilityActivation,
    ConnectorStoreCapabilityPublication,
)
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.downstream_mcp.catalog import StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.permissions import PersonalDownstreamPermissionCatalog
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionReader
from umbod.core.connectors.native.capabilities import (
    NativeCapabilityCatalog,
    NativeCapabilityReadiness,
)
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.permissions import (
    AdminGroupPermissionManagement,
    AssignablePermissionCatalog,
    CapabilityPermissionCatalog,
    CompositeConnectorToolPermissionCatalog,
    GroupPermissionManagementService,
    GroupPermissionStore,
    NoopPermissionChangeNotifier,
)
from umbod.core.permissions.read_state import AssignableReadState
from umbod.core.publishing import ConnectorPublicationReader, ConnectorPublishingStore
from umbod.rest.connectors.dependencies import (
    get_capability_activation_store,
    get_connector_publishing_store,
)
from umbod.rest.connectors.native.dependencies import (
    get_connector_current_configuration_store,
    get_connector_registry,
)
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.mcp_permissions.assignable_reads import (
    PreparedAssignableCatalogs,
    get_assignable_read_state,
    get_prepared_assignable_catalogs,
)


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
    activation_store: Annotated[ActivationStore, Depends(get_capability_activation_store)],
) -> AssignablePermissionCatalog:
    return _native_permission_catalog(
        NativeCapabilityCatalog.from_registry(connector_registry),
        connector_registry, configuration_store, publishing_store, activation_store,
    )


def _native_permission_catalog(
    capabilities: CapabilityCatalog,
    connector_registry: ConnectorRegistry,
    configuration_store: ConnectorCurrentConfigurationStore,
    publishing_store: ConnectorPublicationReader,
    activation_store: CapabilityActivationReader,
) -> AssignablePermissionCatalog:
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
    activation_store: Annotated[ActivationStore, Depends(get_capability_activation_store)],
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories),
    ],
) -> AssignablePermissionCatalog:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    definitions = dependency_factories.downstream_mcp_definition_store.create()
    return _composite_permission_catalog(
        native_catalog,
        StoreBackedOpenApiCapabilityCatalog(await dependency_factories.openapi_connector_store.create()),
        StoreBackedDownstreamCapabilityCatalog(
            definitions, dependency_factories.downstream_mcp_catalog_store.create(),
        ),
        definitions,
        publishing_store,
        activation_store,
    )


def get_assignable_permission_catalog(
    prepared: Annotated[PreparedAssignableCatalogs, Depends(get_prepared_assignable_catalogs)],
    state: Annotated[AssignableReadState, Depends(get_assignable_read_state)],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    configurations: Annotated[
        ConnectorCurrentConfigurationStore, Depends(get_connector_current_configuration_store),
    ],
) -> AssignablePermissionCatalog:
    native_catalog = _native_permission_catalog(
        prepared.native, registry, configurations, state.publishing, state.activations,
    )
    return _composite_permission_catalog(
        native_catalog, prepared.openapi, prepared.downstream, prepared.definitions,
        state.publishing, state.activations,
    )


def _composite_permission_catalog(
    native_catalog: AssignablePermissionCatalog,
    openapi: CapabilityCatalog,
    downstream: CapabilityCatalog,
    definitions: ConnectorDefinitionReader,
    publishing: ConnectorPublicationReader,
    activations: CapabilityActivationReader,
) -> AssignablePermissionCatalog:
    return CompositeConnectorToolPermissionCatalog((
        native_catalog,
        _openapi_permission_catalog(openapi, publishing, activations),
        _downstream_permission_catalog(downstream, definitions, publishing, activations),
    ))


def _openapi_permission_catalog(
    capabilities: CapabilityCatalog,
    publishing: ConnectorPublicationReader,
    activations: CapabilityActivationReader,
) -> AssignablePermissionCatalog:
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
    capabilities: CapabilityCatalog,
    definitions: ConnectorDefinitionReader,
    publishing: ConnectorPublicationReader,
    activations: CapabilityActivationReader,
) -> AssignablePermissionCatalog:
    catalog = CapabilityPermissionCatalog(
        capabilities,
        "downstream_mcp",
        ConnectorStoreCapabilityPublication("downstream_mcp", publishing),
        ConnectorStoreCapabilityActivation("downstream_mcp", activations),
        CatalogCapabilityReadiness(capabilities),
        validate_connector_availability=False,
        validate_tool_availability=False,
        include_connector_without_tools=False,
    )
    return PersonalDownstreamPermissionCatalog(catalog, definitions, publishing)


def get_admin_group_permission_management(
    store: Annotated[GroupPermissionStore, Depends(get_group_permission_store)],
    catalog: Annotated[AssignablePermissionCatalog, Depends(get_connector_permission_catalog)],
) -> AdminGroupPermissionManagement:
    return GroupPermissionManagementService(
        store=store,
        catalog=catalog,
        notifier=NoopPermissionChangeNotifier(),
    )
