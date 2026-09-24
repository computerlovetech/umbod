from fastmcp import FastMCP

from umbod.core.capabilities import (
    CapabilityAvailability,
    CatalogCapabilityReadiness,
    ConnectorStoreCapabilityActivation,
    ConnectorStoreCapabilityPublication,
    UnrestrictedCapabilityPermissionPolicy,
)
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.activation import ActivationStore
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore


def openapi_availability_reader(
    server: FastMCP,
    store: OpenApiConnectorStore,
) -> CapabilityAvailability | None:
    publishing_store: ConnectorPublishingStore | None = getattr(server, 'openapi_publishing_store', None)
    activation_store: ActivationStore | None = getattr(server, 'capability_activation_store', None)
    if publishing_store is None or activation_store is None:
        return None
    catalog = StoreBackedOpenApiCapabilityCatalog(store)
    return CapabilityAvailability(
        ConnectorStoreCapabilityPublication('openapi', publishing_store),
        ConnectorStoreCapabilityActivation('openapi', activation_store),
        CatalogCapabilityReadiness(catalog),
        UnrestrictedCapabilityPermissionPolicy(),
    )
