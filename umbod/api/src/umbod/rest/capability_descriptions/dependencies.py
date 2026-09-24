from typing import Annotated

from fastapi import Depends

from umbod.core.capabilities.descriptions import (
    CapabilityDescriptionOverrideResolver,
    ConnectorCapabilityDescriptionOverrideStore,
)
from umbod.rest.capability_descriptions.base_reader import (
    CompositeConnectorCapabilityBaseDescriptionReader,
)
from umbod.core.connectors.native.registry import ConnectorRegistry
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStore
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.rest.connectors.native.dependencies import get_connector_registry
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.connectors.downstream_mcp.dependencies import get_definition_store
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.connectors.openapi.dependencies import get_openapi_connector_store


async def get_override_store(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorCapabilityDescriptionOverrideStore:
    return await factories.connector_capability_description_override_store.create()


def get_resolver(
    store: Annotated[ConnectorCapabilityDescriptionOverrideStore, Depends(get_override_store)],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    downstream: Annotated[ConnectorDefinitionStore, Depends(get_definition_store)],
    openapi: Annotated[OpenApiConnectorStore, Depends(get_openapi_connector_store)],
) -> CapabilityDescriptionOverrideResolver:
    return CapabilityDescriptionOverrideResolver(
        store,
        CompositeConnectorCapabilityBaseDescriptionReader(registry, downstream, openapi),
    )
