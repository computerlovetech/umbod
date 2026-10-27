from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from umbod.core.capabilities import CachedCapabilityCatalog, CapabilityCatalog
from umbod.core.connectors.downstream_mcp.catalog import StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.catalog.definitions import InMemoryConnectorDefinitionReader
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionReader
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.connectors.native.registry import ConnectorRegistry
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.permissions.read_state import AssignableReadState, plan_assignable_state
from umbod.core.persistence import ReadPlan, TransactionMode
from umbod.infrastructure import create_request_cache
from umbod.rest.connectors.native.dependencies import get_connector_registry
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


@dataclass(frozen=True)
class PreparedAssignableCatalogs:
    native: CapabilityCatalog
    openapi: CapabilityCatalog
    downstream: CapabilityCatalog
    definitions: ConnectorDefinitionReader
    publication_connector_ids: tuple[str, ...]
    activation_connector_ids: tuple[str, ...]


async def get_prepared_assignable_catalogs(
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories),
    ],
) -> PreparedAssignableCatalogs:
    await factories.persistence_runtime.readiness.ensure_ready()
    definition_list = await factories.downstream_mcp_definition_store.create().list()
    definitions = InMemoryConnectorDefinitionReader(definition_list)
    native = NativeCapabilityCatalog.from_registry(registry)
    openapi = CachedCapabilityCatalog(
        StoreBackedOpenApiCapabilityCatalog(await factories.openapi_connector_store.create()),
        create_request_cache(),
    )
    downstream = CachedCapabilityCatalog(
        StoreBackedDownstreamCapabilityCatalog(
            definitions, factories.downstream_mcp_catalog_store.create(),
        ),
        create_request_cache(),
    )
    activation_ids: set[str] = set()
    for catalog in (native, openapi, downstream):
        activation_ids.update(
            capability.identity.connector_id for capability in await catalog.list_capabilities()
        )
    publication_ids = activation_ids.union(
        definition.connector_id for definition in definition_list.definitions
        if uses_personal_oauth(definition)
    )
    return PreparedAssignableCatalogs(
        native=native,
        openapi=openapi,
        downstream=downstream,
        definitions=definitions,
        publication_connector_ids=tuple(sorted(publication_ids)),
        activation_connector_ids=tuple(sorted(activation_ids)),
    )


async def get_assignable_read_state(
    prepared: Annotated[PreparedAssignableCatalogs, Depends(get_prepared_assignable_catalogs)],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories),
    ],
) -> AssignableReadState:
    if not prepared.publication_connector_ids and not prepared.activation_connector_ids:
        return AssignableReadState.empty()
    plan = ReadPlan()
    reads = plan_assignable_state(
        plan, prepared.publication_connector_ids, prepared.activation_connector_ids,
    )
    async with factories.persistence_runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        results = await plan.execute(session)
    return reads.resolve(results)
