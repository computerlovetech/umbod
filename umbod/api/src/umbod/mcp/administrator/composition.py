from collections.abc import Callable
from functools import partial
from uuid import UUID

from umbod.config.defaults import LOCAL_CONNECTOR_CONFIGURATION_SECRET
from umbod.config.identity_policy import filesystem_managed_issuer
from umbod.core.activation.factories import create_capability_activation_store
from umbod.core.administrator import (
    AdministratorAccess,
    AdministratorChanges,
    AdministratorDiscovery,
    AdministratorInspection,
)
from umbod.core.administrator.connector_configuration import AdministratorConnectorConfigurationService
from umbod.core.administrator.connector_configuration.mutation import CatalogAdministratorConfigurationMutation
from umbod.core.administrator.connector_configuration.reader import CatalogAdministratorConnectorConfigurationReader
from umbod.core.administrator.connector_inventory import CatalogConnectorInventory
from umbod.core.capabilities.descriptions.factories import ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory
from umbod.core.configuration import (
    ConnectorConfigurationService,
    ConnectorCurrentConfigurationStore,
    EnvironmentConnectorConfigurationSecret,
)
from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.connectors.downstream_mcp.adapters.settings import downstream_mcp_infrastructure_settings_from_app_config
from umbod.core.connectors.downstream_mcp.catalog import StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.connectors.native.configuration_adapter import ConnectorConfigurationSchemaRegistryAdapter
from umbod.core.connectors.native.registry import ConnectorRegistry, InMemoryConnectorRegistry
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from umbod.core.filesystem.namespaces import (
    CreateSharedNamespace,
    DeleteSharedNamespace,
    NamespaceManagement,
    SaveSharedNamespace,
    SaveSharedNamespaceDescription,
    SharedNamespaceView,
)
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.core.invocation import DatabaseConnectorInvocationPolicyStore
from umbod.core.permissions import GroupPermissionManagementService, NoopPermissionChangeNotifier
from umbod.core.permissions.composition import (
    compose_connector_permission_catalog,
    compose_native_permission_catalog,
)
from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.infrastructure import create_filesystem_namespace_management
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.tools import McpObservedToolRegistrar

from .connector_configuration.catalog import AdministratorConfigurationCatalog
from .operation_facade import AdministratorOperationFacade
from .operation_registration import register_administrator_operation_tools


class _DeferredNamespaceManagement:
    def __init__(self, create_management: Callable[[], NamespaceManagement]) -> None:
        self._create_management = create_management

    async def list(self) -> list[SharedNamespaceView]:
        return await self._create_management().list()

    async def create(self, command: CreateSharedNamespace) -> SharedNamespaceView:
        return await self._create_management().create(command)

    async def save(
        self, namespace_id: UUID, command: SaveSharedNamespace | SaveSharedNamespaceDescription
    ) -> SharedNamespaceView:
        return await self._create_management().save(namespace_id, command)

    async def delete(self, namespace_id: UUID, command: DeleteSharedNamespace) -> None:
        await self._create_management().delete(namespace_id, command)


async def _native_configuration_store(
    runtime: ConnectorRuntime, registry: ConnectorRegistry, settings: MCPAppSettings, database: Database,
) -> ConnectorCurrentConfigurationStore:
    if runtime.connector_configuration_store is not None:
        return runtime.connector_configuration_store
    return ConnectorConfigurationService(
        registry=ConnectorConfigurationSchemaRegistryAdapter(registry),
        store=await create_encrypted_connector_configuration_store(database),
        secret=EnvironmentConnectorConfigurationSecret.from_value(
            settings.connector_security.configuration_secret or LOCAL_CONNECTOR_CONFIGURATION_SECRET
        ),
    )


async def register_configured_administrator_tools(
    registrar: McpObservedToolRegistrar,
    settings: MCPAppSettings,
    runtime: ConnectorRuntime,
    persistence_runtime: PersistenceRuntime,
) -> None:
    database = persistence_runtime.database
    group_permissions = await create_group_permission_store(database)
    openapi = await ConfiguredOpenApiConnectorStoreFactory(database).create()
    downstream = await create_downstream_mcp_stores(
        downstream_mcp_infrastructure_settings_from_app_config(settings).credential_secret,
        database,
    )
    native = InMemoryConnectorRegistry(
        runtime.connector_registrations,
        [str(registration['id']) for registration in runtime.connector_registrations],
    )
    activations = await create_capability_activation_store(database)
    publishing = runtime.connector_publishing_store
    if publishing is None:
        publishing = await create_connector_publishing_store(database)
    native_permissions = compose_native_permission_catalog(
        NativeCapabilityCatalog.from_registry(native), native,
        await _native_configuration_store(runtime, native, settings, database),
        publishing, activations,
    )
    permission_targets = compose_connector_permission_catalog(
        native_permissions,
        StoreBackedOpenApiCapabilityCatalog(openapi),
        StoreBackedDownstreamCapabilityCatalog(downstream.definitions, downstream.catalogs),
        downstream.definitions, publishing, activations,
    )
    permissions = GroupPermissionManagementService(
        group_permissions, permission_targets, NoopPermissionChangeNotifier(),
    )
    catalog = AdministratorConfigurationCatalog(
        lambda: native, openapi, downstream.definitions, downstream.catalogs,
    )
    descriptions = await ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory(database).create()
    reader = CatalogAdministratorConnectorConfigurationReader(
        catalog, activations, DatabaseConnectorInvocationPolicyStore(database),
        descriptions, group_permissions,
    )
    configuration = AdministratorConnectorConfigurationService(
        reader, CatalogAdministratorConfigurationMutation(
            database, catalog, reader, descriptions, group_permissions,
        ),
    )
    namespaces = _DeferredNamespaceManagement(partial(
        create_filesystem_namespace_management,
        database=database,
        issuer=filesystem_managed_issuer(settings),
    ))
    membership_claim = settings.admin_authentication.membership_claim
    required_membership = settings.admin_authentication.required_membership
    access = AdministratorAccess(required_membership)
    facade = AdministratorOperationFacade(
        AdministratorDiscovery(
            access, CatalogConnectorInventory(native, openapi, downstream.definitions, publishing),
            create_group_management(database), permission_targets,
            DatabaseIdentityDirectory(database), namespaces,
            issuer=settings.oidc.issuer_url,
            permission_group_claim=settings.mcp.permission_group_claim,
        ),
        AdministratorInspection(access, configuration, group_permissions),
        AdministratorChanges(access, configuration, permissions, namespaces),
        membership_claim,
    )
    register_administrator_operation_tools(registrar, facade, membership_claim, required_membership)
