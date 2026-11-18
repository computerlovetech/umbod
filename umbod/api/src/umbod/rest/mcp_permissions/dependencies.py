from typing import Annotated

from fastapi import Depends

from umbod.core.activation import ActivationStore
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.downstream_mcp.catalog import StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.connectors.native.registry import ConnectorRegistry
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.permissions import (
    AdminGroupPermissionManagement,
    AssignablePermissionCatalog,
    GroupPermissionManagementService,
    GroupPermissionStore,
    NoopPermissionChangeNotifier,
)
from umbod.core.permissions.composition import (
    compose_connector_permission_catalog,
    compose_native_permission_catalog,
)
from umbod.core.permissions.read_state import AssignableReadState
from umbod.core.publishing import ConnectorPublishingStore
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
    return compose_native_permission_catalog(
        NativeCapabilityCatalog.from_registry(connector_registry),
        connector_registry, configuration_store, publishing_store, activation_store,
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
    return compose_connector_permission_catalog(
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
    native_catalog = compose_native_permission_catalog(
        prepared.native, registry, configurations, state.publishing, state.activations,
    )
    return compose_connector_permission_catalog(
        native_catalog, prepared.openapi, prepared.downstream, prepared.definitions,
        state.publishing, state.activations,
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
