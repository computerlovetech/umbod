from typing import Annotated

from fastapi import Depends

from umbod.core.capabilities import (
    CapabilityAvailability,
    NormalizedCapability,
    CatalogCapabilityReadiness,
    ConnectorStoreCapabilityActivation,
    ConnectorStoreCapabilityPublication,
)
from umbod.core.capabilities.catalog import InMemoryCapabilityCatalog
from umbod.core.capabilities.descriptions import ConnectorCapabilityDescriptionOverrideStore
from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.core.connectors.downstream_mcp.adapters.settings import downstream_mcp_infrastructure_settings_from_app_config
from umbod.core.connectors.downstream_mcp.catalog import StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.catalog.definitions import InMemoryConnectorDefinitionReader
from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.personal_connections import (
    PersonalCaller, PersonalConnectionService, PersonalConnectorInventoryService, ResolvedPersonalIdentity,
)
from umbod.core.connectors.downstream_mcp.user_catalogue import (
    PersonalCatalogueSource, PersonalNamespace, SharedDownstreamCatalogue, SharedDownstreamReadiness,
)
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog, NativeCapabilityReadiness
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.persistence import ReadPlan, TransactionMode
from umbod.core.user_catalogue import CatalogueSource, UserCatalogueReader, UserCatalogueService
from umbod.core.user_catalogue.in_memory import InMemoryCatalogueSource
from umbod.core.user_catalogue.read_state import plan_catalogue_state
from umbod.core.user_catalogue.readiness import RequestConnectorReadiness
from umbod.core.user_catalogue.shared import IndexedCapabilityPermissions, SharedCatalogueSource
from umbod.rest.connectors.dependencies import get_connector_capability_description_override_store
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores
from umbod.rest.connectors.native.dependencies import get_connector_current_configuration_store, get_connector_registry
from umbod.rest.connectors.openapi.dependencies import get_openapi_connector_store
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .caller import CatalogueCaller, get_catalogue_caller
from .projection import CapabilityNameKey, CollisionSafeSource, duplicate_names, gateway_tools_unavailable


async def get_user_catalogue(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    captured: Annotated[CatalogueCaller, Depends(get_catalogue_caller)],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    configurations: Annotated[ConnectorCurrentConfigurationStore, Depends(get_connector_current_configuration_store)],
    openapi: Annotated[OpenApiConnectorStore, Depends(get_openapi_connector_store)],
    descriptions: Annotated[ConnectorCapabilityDescriptionOverrideStore, Depends(get_connector_capability_description_override_store)],
) -> UserCatalogueReader:
    settings = factories.settings
    groups = captured.groups
    definition_list = await factories.downstream_mcp_definition_store.create().list()
    definitions = InMemoryConnectorDefinitionReader(definition_list)
    credentials = factories.downstream_mcp_credential_store.create()
    catalogs = factories.downstream_mcp_catalog_store.create()
    native = NativeCapabilityCatalog.from_registry(registry)
    native_capabilities = await native.list_capabilities()
    openapi_connectors = await openapi.list_connectors()
    connector_ids = tuple(dict.fromkeys((
        *(capability.identity.connector_id for capability in native_capabilities),
        *(connector.connector_id for connector in openapi_connectors),
        *(definition.connector_id for definition in definition_list.definitions),
    )))
    plan = ReadPlan()
    state_reads = plan_catalogue_state(plan, connector_ids, groups.group_ids)
    async with factories.persistence_runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        results = await plan.execute(session)
    state = state_reads.resolve(results)
    publishing = state.publishing
    policy = await IndexedCapabilityPermissions.capture(state.permissions, groups.group_ids)
    api_loader = StoreBackedOpenApiCapabilityCatalog(openapi)
    api_capabilities: list[NormalizedCapability] = []
    for connector in openapi_connectors:
        api_capabilities.extend(await api_loader.list_connector_capabilities(connector))
    api = InMemoryCapabilityCatalog(tuple(api_capabilities))
    downstream = StoreBackedDownstreamCapabilityCatalog(definitions, catalogs)
    downstream_records = await downstream.list_records()
    shared = SharedDownstreamCatalogue(downstream_records)
    shared_readiness = SharedDownstreamReadiness(shared, credentials)
    schemas = {
        definition.metadata.id: definition.configuration_schema
        for definition in registry.list_connector_definitions(ConnectorDefinitionFilter(availability="available"))
    }
    sources: list[CatalogueSource] = []
    for kind, catalog, readiness in (
        ("native", native, RequestConnectorReadiness(NativeCapabilityReadiness(schemas, configurations))),
        ("openapi", api, CatalogCapabilityReadiness(api)),
        ("downstream_mcp", shared, shared_readiness),
    ):
        availability = CapabilityAvailability(
            ConnectorStoreCapabilityPublication(kind, publishing),
            ConnectorStoreCapabilityActivation(kind, state.activations), readiness, policy,
        )
        sources.append(SharedCatalogueSource(catalog, availability, descriptions))
    names: dict[CapabilityNameKey, str] = {}
    gateway = settings.mcp.connector_tool_exposure_mode in ("gateway", "codemode")
    for binding in native_capabilities:
        identity = binding.identity
        if identity.capability_kind == "tool" and (gateway or await publishing.is_published(identity.connector_id)):
            names[("native", identity.connector_id, "tool", identity.capability_key)] = native.resolve_binding(identity).public_tool_name
    api_prefixes = {connector.connector_id: connector.tool_name_prefix for connector in openapi_connectors}
    for capability in api_capabilities:
        identity = capability.identity
        if await publishing.is_published(identity.connector_id):
            names[("openapi", identity.connector_id, "tool", identity.capability_key)] = mangle_public_tool_name(
                api_prefixes[identity.connector_id], identity.capability_key,
            )
    for record in downstream_records:
        identity = record.capability.identity
        if uses_personal_oauth(record.definition) or not await publishing.is_published(identity.connector_id):
            continue
        if identity.capability_kind != "tool" and not await shared_readiness.is_ready(identity):
            continue
        name = (
            mangle_public_tool_name(record.definition.tool_name_prefix, identity.capability_key)
            if identity.capability_kind == "tool"
            else mangle_public_tool_name(identity.connector_id, identity.capability_key)
            if identity.capability_kind == "prompt" else identity.capability_key
        )
        names[("downstream_mcp", identity.connector_id, identity.capability_kind, identity.capability_key)] = name
    if settings.personal_connections.enabled:
        resolution = captured.personal_identity
        if isinstance(resolution, ResolvedPersonalIdentity):
            personal_caller = PersonalCaller(caller=captured.caller, principal=resolution.principal, groups=groups)
            stores = await get_downstream_stores(
                downstream_mcp_infrastructure_settings_from_app_config(settings), factories,
            )
            inventory = PersonalConnectorInventoryService(
                definitions, publishing, state.permissions, groups,
                PersonalConnectionService(personal_caller, stores.personal_connections), descriptions,
            )
            personal_source = PersonalCatalogueSource(
                inventory, stores.personal_tool_access, personal_caller.principal, groups.group_ids,
                settings.personal_connections.oauth_enabled, utc_clock,
            )
            personal_connectors = await personal_source.list_connectors()
            sources.append(InMemoryCatalogueSource(personal_connectors))
            by_id = {definition.connector_id: definition for definition in definition_list.definitions}
            for connector in personal_connectors:
                for capability in connector.capabilities:
                    names[("downstream_mcp", connector.connector_id, "tool", capability.key)] = mangle_public_tool_name(
                        by_id[connector.connector_id].tool_name_prefix, capability.key,
                    )
    namespace = PersonalNamespace(definition_list.definitions)
    blocked = duplicate_names(names)
    personal_ids = {
        definition.connector_id for definition in definition_list.definitions
        if uses_personal_oauth(definition)
    }
    invalid_shared_tools = any(
        identity in blocked or not namespace.allows(name, identity[1], False)
        for identity, name in names.items()
        if identity[0] == "downstream_mcp" and identity[2] == "tool" and identity[1] not in personal_ids
    )
    if invalid_shared_tools:
        blocked = blocked.union(
            identity for identity in names if identity[0] == "downstream_mcp" and identity[2] == "tool"
        )
    if gateway and gateway_tools_unavailable(names, namespace, frozenset(personal_ids)):
        blocked = blocked.union(identity for identity in names if identity[2] == "tool")
    return UserCatalogueService(
        tuple(CollisionSafeSource(source, names, namespace, blocked) for source in sources),
        settings.personal_connections.enabled, captured.identity_key,
    )
