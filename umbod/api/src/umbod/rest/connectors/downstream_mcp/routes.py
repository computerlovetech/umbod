from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from messaging.ports import EventStream

from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    OverriddenCapabilityDescription,
    SetCapabilityDescriptionOverride,
)
from umbod.core.identity import (
    ConnectorIdentityConflictError,
)
from umbod.core.capabilities.tools.names import PublicToolNameConflictError
from umbod.core.invocation import (
    ConnectorInvocationPolicyStore,
)
from umbod.core.activation.events import connector_capability_activation_changed_event
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolConfigurationMutationPort
from umbod.core.activation import (
    ActivationListFilter,
    ActivationPort,
    ActivationStatus,
    ActivationStore,
    CapabilityActivationService,
    CapabilityActivationState,
    CapabilityRef,
    InMemoryActivationNotifier,
    KeySetActivationCatalog,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    ConnectorUnhealthy,
    NoAuthCreateConnectorDefinition,
    StaticBearerCreateConnectorDefinition,
    DiscoveryFailed,
    DiscoveredToolWithOutputSchema,
    NoAuthConnectorDefinition,
    StaticBearerConnectorDefinition,
)
from umbod.core.connectors.downstream_mcp.activation import (
    DownstreamActivationEventPublicationPolicy,
)
from umbod.core.connectors.downstream_mcp.catalog import (
    DownstreamConnectorCatalogLifecycle,
)
from umbod.core.connectors.downstream_mcp.errors import (
    DownstreamConnectorConflictError,
    DownstreamConnectorNotFoundError,
    DownstreamPermissionGrantConflict,
)
from umbod.core.connectors.downstream_mcp.management import (
    DownstreamConnectorCreator,
    DownstreamConnectorDeleter,
    DownstreamConnectorQueries,
    DownstreamConnectorUpdater,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DownstreamConnectorValidationError,
)
from umbod.core.connectors.downstream_mcp.publishing import DownstreamConnectorPublisher
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorHealthFound,
    ToolCatalogFound,
)
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.connectors.dependencies import (
    get_capability_activation_store,
    get_connector_event_stream,
    get_connector_invocation_policy_store,
    get_connector_tool_configuration_mutation_port,
)
from umbod.rest.connectors.schemas import (
    ConnectorToolInvocationPolicyConflictResponse,
    OverriddenInitialCapabilityDescriptionOverride,
)
from umbod.rest.connectors.tool_activation import list_tool_activations, put_tool_activations
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.connectors.downstream_mcp.dependencies import (
    get_downstream_connector_catalog_lifecycle,
    get_downstream_connector_creator,
    get_downstream_connector_deleter,
    get_downstream_connector_publisher,
    get_downstream_connector_queries,
    get_downstream_connector_updater,
    get_downstream_tool_activation_port,
)
from umbod.rest.connectors.downstream_mcp.errors import (
    present_discovery_failure,
    present_downstream_mcp_error,
    present_tool_not_found,
)
from umbod.rest.connectors.downstream_mcp.schemas import (
    BearerCreateConfigurationRequest,
    CapabilityDescriptionOverrideResponse,
    OverriddenCapabilityDescriptionOverrideResponse,
    SystemCapabilityDescriptionOverrideResponse,
    ConnectorHealthResponse,
    ConnectorListResponse,
    ConnectorMetadataPatchRequest,
    ConnectorConfigurationRequest,
    ConnectorConfigurationResponse,
    ConnectorResponse,
    ConnectorSummaryResponse,
    CreateConnectorRequest,
    PromptActivationBatchRequest,
    PromptActivationBatchResponse,
    PromptActivationBatchResponseItem,
    PromptArgumentResponse,
    PromptCatalogResponse,
    PromptResponse,
    PublicationResponse,
    ResourceActivationBatchRequest,
    ResourceActivationBatchResponse,
    ResourceActivationBatchResponseItem,
    ResourceCatalogResponse,
    ResourceResponse,
    ToolActivationBatchRequest,
    ToolActivationBatchResponse,
    ToolListResponse,
    ToolResponse,
)


router = APIRouter(prefix="/connectors/mcp", tags=["downstream-mcp-connectors"])
Queries = Annotated[DownstreamConnectorQueries, Depends(get_downstream_connector_queries)]
Creator = Annotated[DownstreamConnectorCreator, Depends(get_downstream_connector_creator)]
Updater = Annotated[DownstreamConnectorUpdater, Depends(get_downstream_connector_updater)]
CatalogLifecycle = Annotated[
    DownstreamConnectorCatalogLifecycle, Depends(get_downstream_connector_catalog_lifecycle)
]
Publisher = Annotated[DownstreamConnectorPublisher, Depends(get_downstream_connector_publisher)]
Deleter = Annotated[DownstreamConnectorDeleter, Depends(get_downstream_connector_deleter)]
ActivationPort = Annotated[
    ActivationPort, Depends(get_downstream_tool_activation_port)
]
PolicyStore = Annotated[
    ConnectorInvocationPolicyStore, Depends(get_connector_invocation_policy_store)
]
ToolConfigurationMutation = Annotated[
    ConnectorToolConfigurationMutationPort,
    Depends(get_connector_tool_configuration_mutation_port),
]
ConnectorEventStream = Annotated[EventStream | None, Depends(get_connector_event_stream)]


def get_public_mcp_base_url(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> str:
    return factories.settings.endpoints.mcp_base_url.rstrip("/")


async def get_capability_description_override_store(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorCapabilityDescriptionOverrideStore:
    return await factories.connector_capability_description_override_store.create()


PublicMcpBaseUrl = Annotated[str, Depends(get_public_mcp_base_url)]
OverrideStore = Annotated[
    ConnectorCapabilityDescriptionOverrideStore, Depends(get_capability_description_override_store)
]


def _create_definition(
    request: CreateConnectorRequest,
) -> NoAuthCreateConnectorDefinition | StaticBearerCreateConnectorDefinition:
    metadata = request.metadata
    configuration = request.configuration
    shared = dict(
        display_name=metadata.display_name,
        tool_name_prefix=metadata.tool_name_prefix,
        capability_description=metadata.capability_description,
        endpoint_url=configuration.endpoint_url,
        public_path=metadata.public_path,
    )
    if isinstance(configuration, BearerCreateConfigurationRequest):
        return StaticBearerCreateConnectorDefinition(
            **shared,
            bearer_token=configuration.bearer_token,
            header_type=configuration.header_type,
            custom_header_name=configuration.custom_header_name,
        )
    return NoAuthCreateConnectorDefinition(**shared)


async def _response(
    queries: DownstreamConnectorQueries,
    definition: ConnectorDefinition,
    public_mcp_base_url: str,
    override_store: ConnectorCapabilityDescriptionOverrideStore,
) -> ConnectorResponse:
    key = ConnectorCapabilityDescriptionKey(
        kind="downstream_mcp", connector_id=definition.connector_id
    )
    override = await override_store.get(key)
    if isinstance(override, OverriddenCapabilityDescription):
        effective_description = override.description
        override_response: CapabilityDescriptionOverrideResponse = (
            OverriddenCapabilityDescriptionOverrideResponse(
                description=override.description,
                revision=override.revision,
            )
        )
    else:
        effective_description = definition.capability_description
        override_response = SystemCapabilityDescriptionOverrideResponse(revision=override.revision)
    health_result = await queries.health(definition.connector_id)
    if isinstance(health_result, ConnectorHealthFound):
        health = health_result.health
        health_response = ConnectorHealthResponse(
            status=health.status,
            checked_at=health.checked_at,
            reason=health.reason if isinstance(health, ConnectorUnhealthy) else None,
        )
    else:
        health_response = ConnectorHealthResponse(status="unknown")
    catalog_result = await queries.catalog(definition.connector_id)
    icon_url = (
        catalog_result.snapshot.server_icons[0].src
        if isinstance(catalog_result, ToolCatalogFound) and catalog_result.snapshot.server_icons
        else ""
    )
    return ConnectorResponse(
        connector_id=definition.connector_id,
        display_name=definition.display_name,
        tool_name_prefix=definition.tool_name_prefix,
        icon_url=icon_url,
        capability_description=effective_description,
        base_capability_description=definition.capability_description,
        effective_capability_description=effective_description,
        capability_description_override=override_response,
        endpoint_url=definition.endpoint_url,
        public_path=definition.public_path,
        public_url=f"{public_mcp_base_url}{definition.public_path}",
        auth_mode=definition.auth_type,
        header_type=(
            definition.header_type
            if isinstance(definition, StaticBearerConnectorDefinition)
            else "bearer"
        ),
        custom_header_name=(
            definition.custom_header_name
            if isinstance(definition, StaticBearerConnectorDefinition)
            else None
        ),
        credential_configured=await queries.credential_configured(definition.connector_id),
        publication_status=(
            "published" if await queries.is_published(definition.connector_id) else "unpublished"
        ),
        health=health_response,
    )


async def _summary_response(
    queries: DownstreamConnectorQueries,
    definition: ConnectorDefinition,
) -> ConnectorSummaryResponse:
    health_result = await queries.health(definition.connector_id)
    if isinstance(health_result, ConnectorHealthFound):
        health = health_result.health
        health_response = ConnectorHealthResponse(
            status=health.status,
            checked_at=health.checked_at,
            reason=health.reason if isinstance(health, ConnectorUnhealthy) else None,
        )
    else:
        health_response = ConnectorHealthResponse(status="unknown")
    catalog_result = await queries.catalog(definition.connector_id)
    icon_url = (
        catalog_result.snapshot.server_icons[0].src
        if isinstance(catalog_result, ToolCatalogFound) and catalog_result.snapshot.server_icons
        else ""
    )
    return ConnectorSummaryResponse(
        connector_id=definition.connector_id,
        display_name=definition.display_name,
        icon_url=icon_url,
        auth_mode=definition.auth_type,
        publication_status=(
            "published" if await queries.is_published(definition.connector_id) else "unpublished"
        ),
        health=health_response,
    )


@router.get("", response_model=ConnectorListResponse)
async def list_connectors(queries: Queries) -> ConnectorListResponse:
    return ConnectorListResponse(
        connectors=tuple(
            [await _summary_response(queries, item) for item in (await queries.list()).definitions]
        )
    )


@router.post("", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    request: CreateConnectorRequest,
    creator: Creator,
    queries: Queries,
    deleter: Deleter,
    public_mcp_base_url: PublicMcpBaseUrl,
    override_store: OverrideStore,
) -> ConnectorResponse:
    try:
        definition = await creator.create(_create_definition(request))
        try:
            if isinstance(
                request.capability_description_override,
                OverriddenInitialCapabilityDescriptionOverride,
            ):
                await override_store.set(
                    SetCapabilityDescriptionOverride(
                        key=ConnectorCapabilityDescriptionKey(
                            kind="downstream_mcp", connector_id=definition.connector_id
                        ),
                        description=request.capability_description_override.description,
                        expected_revision=0,
                    )
                )
        except Exception:
            await deleter.delete(definition.connector_id)
            raise
        return await _response(queries, definition, public_mcp_base_url, override_store)
    except (
        ConnectorIdentityConflictError,
        DownstreamConnectorConflictError,
        DownstreamConnectorValidationError,
    ) as error:
        raise present_downstream_mcp_error(error) from error
    except ValueError as error:
        raise present_downstream_mcp_error(error) from error


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: str,
    queries: Queries,
    public_mcp_base_url: PublicMcpBaseUrl,
    override_store: OverrideStore,
) -> ConnectorResponse:
    try:
        return await _response(
            queries, await queries.get(connector_id), public_mcp_base_url, override_store
        )
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error


CapabilityActivations = Annotated[ActivationStore, Depends(get_capability_activation_store)]


@router.get("/{connector_id}/prompts", response_model=PromptCatalogResponse)
async def list_prompts(
    connector_id: str, queries: Queries, activations: CapabilityActivations
) -> PromptCatalogResponse:
    try:
        result = await queries.catalog(connector_id)
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error
    if not isinstance(result, ToolCatalogFound):
        return PromptCatalogResponse(prompts=(), available_actions=())
    prompts = []
    for prompt in result.snapshot.prompts:
        status = await activations.get_status(
            CapabilityRef(
                connector_kind="downstream_mcp",
                connector_id=connector_id,
                capability_kind="prompt",
                capability_key=prompt.name,
            )
        )
        prompts.append(
            PromptResponse(
                name=prompt.name,
                description=prompt.description,
                arguments=tuple(
                    PromptArgumentResponse(
                        name=argument.name,
                        description=argument.description,
                        required=argument.required,
                    )
                    for argument in prompt.arguments
                ),
                activation_status=status.value,
            )
        )
    return PromptCatalogResponse(
        prompts=tuple(prompts),
        available_actions=("activate",) if prompts else (),
    )


@router.put("/{connector_id}/prompts/activation", response_model=PromptActivationBatchResponse)
async def set_prompt_activations(
    connector_id: str,
    request: PromptActivationBatchRequest,
    queries: Queries,
    activations: CapabilityActivations,
    event_stream: ConnectorEventStream,
) -> PromptActivationBatchResponse:
    try:
        result = await queries.catalog(connector_id)
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error
    if not isinstance(result, ToolCatalogFound):
        raise present_downstream_mcp_error(DownstreamConnectorNotFoundError(connector_id))
    known = {prompt.name for prompt in result.snapshot.prompts}
    catalog = KeySetActivationCatalog(
        activations, "downstream_mcp", {connector_id: {"prompt": tuple(known)}}
    )
    port = CapabilityActivationService(catalog, activations, InMemoryActivationNotifier())
    states = tuple(
        CapabilityActivationState(
            ref=CapabilityRef(
                connector_kind="downstream_mcp",
                connector_id=connector_id,
                capability_kind="prompt",
                capability_key=item.prompt_id,
            ),
            activation_status=ActivationStatus(item.activation_status),
        )
        for item in request.prompts
    )
    batch = await port.set_statuses(states)
    if batch.failure is not None:
        raise HTTPException(status_code=404, detail=batch.failure.message)
    if event_stream is not None:
        for state in batch.changed_states:
            await event_stream.append(
                connector_capability_activation_changed_event(
                    state.ref.connector_kind,
                    state.ref.connector_id,
                    state.ref.capability_kind,
                    state.ref.capability_key,
                )
            )
    return PromptActivationBatchResponse(
        connector_id=connector_id,
        prompts=tuple(
            PromptActivationBatchResponseItem(
                prompt_id=state.ref.capability_key,
                activation_status=state.activation_status.value,
            )
            for state in batch.states
        ),
    )


@router.get("/{connector_id}/resources", response_model=ResourceCatalogResponse)
async def list_resources(
    connector_id: str, queries: Queries, activations: CapabilityActivations
) -> ResourceCatalogResponse:
    try:
        result = await queries.catalog(connector_id)
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error
    if not isinstance(result, ToolCatalogFound):
        return ResourceCatalogResponse(resources=(), available_actions=())
    resources = []
    for resource in result.snapshot.resources:
        status = await activations.get_status(
            CapabilityRef(
                connector_kind="downstream_mcp",
                connector_id=connector_id,
                capability_kind="resource",
                capability_key=resource.uri,
            )
        )
        resources.append(
            ResourceResponse(
                kind="resource",
                name=resource.name,
                description=resource.description,
                uri=resource.uri,
                activation_status=status.value,
            )
        )
    for template in result.snapshot.resource_templates:
        status = await activations.get_status(
            CapabilityRef(
                connector_kind="downstream_mcp",
                connector_id=connector_id,
                capability_kind="resource_template",
                capability_key=template.uri_template,
            )
        )
        resources.append(
            ResourceResponse(
                kind="resource_template",
                name=template.name,
                description=template.description,
                uri=template.uri_template,
                activation_status=status.value,
            )
        )
    return ResourceCatalogResponse(
        resources=tuple(resources),
        available_actions=("activate",) if resources else (),
    )


@router.put("/{connector_id}/resources/activation", response_model=ResourceActivationBatchResponse)
async def set_resource_activations(
    connector_id: str,
    request: ResourceActivationBatchRequest,
    queries: Queries,
    activations: CapabilityActivations,
    event_stream: ConnectorEventStream,
) -> ResourceActivationBatchResponse:
    try:
        result = await queries.catalog(connector_id)
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error
    if not isinstance(result, ToolCatalogFound):
        raise present_downstream_mcp_error(DownstreamConnectorNotFoundError(connector_id))
    known = {
        "resource": tuple(resource.uri for resource in result.snapshot.resources),
        "resource_template": tuple(
            template.uri_template for template in result.snapshot.resource_templates
        ),
    }
    catalog = KeySetActivationCatalog(activations, "downstream_mcp", {connector_id: known})
    port = CapabilityActivationService(catalog, activations, InMemoryActivationNotifier())
    states = tuple(
        CapabilityActivationState(
            ref=CapabilityRef(
                connector_kind="downstream_mcp",
                connector_id=connector_id,
                capability_kind=item.kind,
                capability_key=item.resource_id,
            ),
            activation_status=ActivationStatus(item.activation_status),
        )
        for item in request.resources
    )
    batch = await port.set_statuses(states)
    if batch.failure is not None:
        raise HTTPException(status_code=404, detail=batch.failure.message)
    if event_stream is not None:
        for state in batch.changed_states:
            await event_stream.append(
                connector_capability_activation_changed_event(
                    state.ref.connector_kind,
                    state.ref.connector_id,
                    state.ref.capability_kind,
                    state.ref.capability_key,
                )
            )
    return ResourceActivationBatchResponse(
        connector_id=connector_id,
        resources=tuple(
            ResourceActivationBatchResponseItem(
                resource_id=state.ref.capability_key,
                kind=state.ref.capability_kind,
                activation_status=state.activation_status.value,
            )
            for state in batch.states
        ),
    )


def _definition_with_configuration(
    current: ConnectorDefinition, request: ConnectorConfigurationRequest
) -> ConnectorDefinition:
    values = dict(
        connector_id=current.connector_id,
        display_name=current.display_name,
        tool_name_prefix=current.tool_name_prefix,
        capability_description=current.capability_description,
        endpoint_url=request.endpoint_url,
        public_path=current.public_path,
    )
    if request.auth_mode == "static_bearer":
        return StaticBearerConnectorDefinition(
            **values,
            header_type=request.header_type,
            custom_header_name=request.custom_header_name,
        )
    return NoAuthConnectorDefinition(**values)


@router.patch("/{connector_id}", response_model=ConnectorResponse)
async def patch_connector(
    connector_id: str,
    request: ConnectorMetadataPatchRequest,
    queries: Queries,
    updater: Updater,
    public_mcp_base_url: PublicMcpBaseUrl,
    override_store: OverrideStore,
) -> ConnectorResponse:
    try:
        current = await queries.get(connector_id)
        definition = current.model_copy(update=request.model_dump(exclude_unset=True))
        updated = await updater.update(current, definition, "")
        return await _response(queries, updated, public_mcp_base_url, override_store)
    except (
        DownstreamConnectorNotFoundError,
        DownstreamConnectorValidationError,
        ValueError,
    ) as error:
        raise present_downstream_mcp_error(error) from error


async def _configuration_response(
    connector_id: str, queries: DownstreamConnectorQueries
) -> ConnectorConfigurationResponse:
    definition = await queries.get(connector_id)
    configured = await queries.credential_configured(connector_id)
    return ConnectorConfigurationResponse(
        endpoint_url=definition.endpoint_url,
        auth_mode=definition.auth_type,
        header_type=(
            definition.header_type
            if isinstance(definition, StaticBearerConnectorDefinition)
            else "bearer"
        ),
        custom_header_name=(
            definition.custom_header_name
            if isinstance(definition, StaticBearerConnectorDefinition)
            else None
        ),
        credential_configured=configured,
    )


@router.put("/{connector_id}/configuration", response_model=ConnectorConfigurationResponse)
async def put_configuration(
    connector_id: str,
    request: ConnectorConfigurationRequest,
    queries: Queries,
    updater: Updater,
) -> ConnectorConfigurationResponse:
    try:
        current = await queries.get(connector_id)
        await updater.update(
            current, _definition_with_configuration(current, request), request.bearer_token or ""
        )
        return await _configuration_response(connector_id, queries)
    except (
        DownstreamConnectorNotFoundError,
        DownstreamConnectorValidationError,
        ValueError,
    ) as error:
        raise present_downstream_mcp_error(error) from error


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: str, deleter: Deleter, override_store: OverrideStore
) -> Response:
    try:
        await deleter.delete(connector_id)
        await override_store.delete(
            ConnectorCapabilityDescriptionKey(kind="downstream_mcp", connector_id=connector_id)
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except DownstreamConnectorNotFoundError as error:
        await override_store.delete(
            ConnectorCapabilityDescriptionKey(kind="downstream_mcp", connector_id=connector_id)
        )
        raise present_downstream_mcp_error(error) from error
    except DownstreamPermissionGrantConflict as error:
        raise present_downstream_mcp_error(error) from error


@router.post("/{connector_id}/discoveries", response_model=ConnectorResponse)
async def refresh_discovery(
    connector_id: str,
    queries: Queries,
    lifecycle: CatalogLifecycle,
    public_mcp_base_url: PublicMcpBaseUrl,
    override_store: OverrideStore,
) -> ConnectorResponse:
    try:
        result = await lifecycle.refresh(connector_id)
        if isinstance(result, DiscoveryFailed):
            raise present_discovery_failure(connector_id)
        return await _response(
            queries, await queries.get(connector_id), public_mcp_base_url, override_store
        )
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error
    except ValueError as error:
        raise present_downstream_mcp_error(error) from error


@router.get("/{connector_id}/tools", response_model=ToolListResponse)
async def list_tools(
    connector_id: str, queries: Queries, activation: ActivationPort
) -> ToolListResponse:
    try:
        result = await queries.catalog(connector_id)
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error
    if not isinstance(result, ToolCatalogFound):
        return ToolListResponse(tools=())
    activation_status_by_name = {
        tool.ref.capability_key: tool.activation_status
        for tool in await activation.list_activations(connector_id, "tool", ActivationListFilter())
    }
    return ToolListResponse(
        discovered_at=result.snapshot.discovered_at,
        tools=tuple(
            ToolResponse(
                name=tool.identity.downstream_name,
                title=tool.title,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=(
                    tool.output_schema if isinstance(tool, DiscoveredToolWithOutputSchema) else None
                ),
                activation_status=activation_status_by_name[tool.identity.downstream_name].value,
            )
            for tool in result.snapshot.tools
        ),
    )


@router.put("/{connector_id}/publication", response_model=PublicationResponse)
async def publish_connector(connector_id: str, publisher: Publisher) -> PublicationResponse:
    try:
        await publisher.publish(connector_id)
    except (PublicToolNameConflictError, DownstreamConnectorConflictError) as error:
        raise present_downstream_mcp_error(error) from error
    return PublicationResponse(connector_id=connector_id, publication_status="published")


@router.delete("/{connector_id}/publication", response_model=PublicationResponse)
async def unpublish_connector(connector_id: str, publisher: Publisher) -> PublicationResponse:
    await publisher.unpublish(connector_id)
    return PublicationResponse(connector_id=connector_id, publication_status="unpublished")


@router.get(
    "/{connector_id}/tools/activation",
    response_model=ToolActivationBatchResponse,
)
async def get_tool_activations(
    connector_id: str,
    queries: Queries,
    activation: ActivationPort,
    policy_store: PolicyStore,
) -> ToolActivationBatchResponse:
    try:
        result = await queries.catalog(connector_id)
    except DownstreamConnectorNotFoundError as error:
        raise present_downstream_mcp_error(error) from error
    operation_names = (
        tuple(tool.identity.downstream_name for tool in result.snapshot.tools)
        if isinstance(result, ToolCatalogFound)
        else ()
    )
    return await list_tool_activations(
        connector_kind="downstream_mcp",
        connector_id=connector_id,
        activation_port=activation,
        policy_store=policy_store,
        operation_names=operation_names,
    )


@router.put(
    "/{connector_id}/tools/activation",
    response_model=ToolActivationBatchResponse,
    responses={409: {"model": ConnectorToolInvocationPolicyConflictResponse}},
)
async def set_tool_activations(
    connector_id: str,
    request: ToolActivationBatchRequest,
    queries: Queries,
    mutation_port: ToolConfigurationMutation,
    event_stream: ConnectorEventStream,
) -> ToolActivationBatchResponse | JSONResponse:
    catalog = await queries.catalog(connector_id)
    operation_names = (
        tuple(tool.identity.downstream_name for tool in catalog.snapshot.tools)
        if isinstance(catalog, ToolCatalogFound)
        else ()
    )
    unknown = next(
        (item.tool_id for item in request.tools if item.tool_id not in operation_names),
        None,
    )
    return await put_tool_activations(
        connector_kind="downstream_mcp",
        connector_id=connector_id,
        items=request.tools,
        known_operation_names=operation_names,
        mutation_port=mutation_port,
        event_stream=event_stream,
        activation_event_policy=DownstreamActivationEventPublicationPolicy(queries),
        unknown_tool_error=(
            present_tool_not_found(connector_id, unknown) if unknown is not None else None
        ),
    )
