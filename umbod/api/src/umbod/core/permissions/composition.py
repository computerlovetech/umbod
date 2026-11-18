from umbod.core.activation.domain import CapabilityActivationReader
from umbod.core.capabilities import (
    CapabilityCatalog,
    CatalogCapabilityReadiness,
    ConnectorStoreCapabilityActivation,
    ConnectorStoreCapabilityPublication,
)
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.downstream_mcp.permissions import PersonalDownstreamPermissionCatalog
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionReader
from umbod.core.connectors.native.capabilities import NativeCapabilityReadiness
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.permissions.catalog import (
    CapabilityPermissionCatalog,
    CompositeConnectorToolPermissionCatalog,
)
from umbod.core.permissions.ports import AssignablePermissionCatalog
from umbod.core.publishing import ConnectorPublicationReader


def compose_native_permission_catalog(
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


def compose_connector_permission_catalog(
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
