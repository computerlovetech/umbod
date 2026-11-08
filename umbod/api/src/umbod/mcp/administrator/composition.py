from functools import partial

from umbod.core.activation.factories import create_capability_activation_store
from umbod.core.administrator.connector_configuration import AdministratorConnectorConfigurationService
from umbod.core.administrator.connector_configuration.mutation import CatalogAdministratorConfigurationMutation
from umbod.core.administrator.connector_configuration.reader import CatalogAdministratorConnectorConfigurationReader
from umbod.core.capabilities.descriptions.factories import ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory
from umbod.core.connectors.downstream_mcp.adapters.settings import downstream_mcp_infrastructure_settings_from_app_config
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.connectors.native.registry import InMemoryConnectorRegistry
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from umbod.core.invocation import DatabaseConnectorInvocationPolicyStore
from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.persistence import PersistenceRuntime
from umbod.mcp.administrator.catalog import AdministratorConfigurationCatalog
from umbod.mcp.administrator.connector_configuration import register_administrator_connector_configuration_tools
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.tools import McpObservedToolRegistrar


async def register_configured_administrator_tools(
    registrar: McpObservedToolRegistrar,
    settings: MCPAppSettings,
    runtime: ConnectorRuntime,
    persistence_runtime: PersistenceRuntime,
) -> None:
    database = persistence_runtime.database
    group_permission_store = await create_group_permission_store(database)
    openapi_connector_store = await ConfiguredOpenApiConnectorStoreFactory(database).create()
    downstream_stores = await create_downstream_mcp_stores(
        downstream_mcp_infrastructure_settings_from_app_config(settings).credential_secret,
        database,
    )
    catalog = AdministratorConfigurationCatalog(
        partial(
            InMemoryConnectorRegistry,
            runtime.connector_registrations,
            [str(registration['id']) for registration in runtime.connector_registrations],
        ),
        openapi_connector_store,
        downstream_stores.definitions,
        downstream_stores.catalogs,
    )
    descriptions = await ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory(database).create()
    reader = CatalogAdministratorConnectorConfigurationReader(
        catalog,
        await create_capability_activation_store(database),
        DatabaseConnectorInvocationPolicyStore(database),
        descriptions,
        group_permission_store,
    )
    mutation = CatalogAdministratorConfigurationMutation(
        database, catalog, reader, descriptions, group_permission_store,
    )
    register_administrator_connector_configuration_tools(
        registrar,
        AdministratorConnectorConfigurationService(reader, mutation),
        settings.admin_authentication.membership_claim,
        settings.admin_authentication.required_membership,
    )
