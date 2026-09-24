from typing import Annotated

from messaging.ports import EventStream
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from umbod.core.configuration import (
    ConnectorCurrentConfigurationStore,
    configuration_fields_from_schema,
    masked_configuration_dump,
    save_connector_configuration,
    validate_connector_configuration_input,
)
from umbod.core.connectors.native.models import ConnectorConfigurationCheckResult
from umbod.core.invocation import (
    ConnectorInvocationPolicyStore,
)
from umbod.core.activation.events import connector_capability_activation_changed_event
from umbod.core.configuration.events import connector_configuration_changed_event
from umbod.core.publishing.events import connector_publication_changed_event
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.invocation.tools.configuration import AlwaysPublishActivationEvents
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolConfigurationMutationPort
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.activation import (
    ActivationFilter,
    ActivationListFilter,
    ActivationPort,
    ActivationStatus,
    CapabilityActivationState,
    CapabilityRef,
)
from umbod.rest.connectors.dependencies import (
    get_connector_event_stream,
    get_connector_invocation_policy_store,
    get_connector_publishing_store,
    get_connector_tool_configuration_mutation_port,
)
from umbod.rest.connectors.schemas import ConnectorToolInvocationPolicyConflictResponse
from umbod.rest.connectors.native.dependencies import (
    ConnectorConfigurationSaveDependencies,
    ConnectorPublicationDependencies,
    get_capability_activation_filter,
    get_capability_activation_port,
    get_connector_configuration_save_dependencies,
    get_connector_current_configuration_store,
    get_connector_presentation_service,
    get_connector_publication_dependencies,
    get_connector_registry,
)
from umbod.rest.connectors.native.schemas import (
    ConnectorConfigurationConnectorSummary,
    ConnectorConfigurationPageResponse,
    ConnectorConfigurationSaveRequest,
    ConnectorConfigurationSaveResponse,
    ConnectorConfigurationSchemaResponse,
    ConnectorDetailResponse,
    ConnectorListResponse,
    ConnectorPublicationResponse,
    ConnectorPromptActivationBatchRequest,
    ConnectorPromptActivationBatchResponse,
    ConnectorPromptActivationBatchResponseItem,
    ConnectorPromptArgumentResponse,
    ConnectorPromptListResponse,
    ConnectorPromptResponse,
    ConnectorResourceActivationBatchRequest,
    ConnectorResourceActivationBatchResponse,
    ConnectorResourceActivationBatchResponseItem,
    ConnectorResourceListResponse,
    ConnectorResourceResponse,
    ConnectorToolActivationBatchRequest,
    ConnectorToolActivationListResponse,
)
from umbod.rest.connectors.native.service import ConnectorPresentationService
from umbod.rest.connectors.tool_activation import list_tool_activations, put_tool_activations


router = APIRouter(prefix="/connectors/catalog", tags=["connectors"])


@router.get("")
async def list_connectors(
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    presentation_service: Annotated[
        ConnectorPresentationService, Depends(get_connector_presentation_service)
    ],
) -> ConnectorListResponse:
    return ConnectorListResponse(
        connectors=[
            await presentation_service.list_item(connector_definition.metadata)
            for connector_definition in connector_registry.list_connector_definitions(
                ConnectorDefinitionFilter(availability="available")
            )
        ]
    )


@router.get("/{connector_id}/configuration")
async def get_connector_configuration(
    connector_id: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    store: Annotated[
        ConnectorCurrentConfigurationStore,
        Depends(get_connector_current_configuration_store),
    ],
) -> ConnectorConfigurationPageResponse:
    connector_definition = connector_registry.get_connector_definition(
        connector_id, ConnectorDefinitionFilter(availability="available")
    )
    if connector_definition is None:
        raise HTTPException(status_code=404, detail="Connector is not available for configuration")
    current_configuration = await store.get_current_configuration(connector_id)
    masked_configuration = (
        None if current_configuration is None else masked_configuration_dump(current_configuration)
    )
    return ConnectorConfigurationPageResponse(
        connector=ConnectorConfigurationConnectorSummary(
            id=connector_definition.metadata.id,
            display_name=connector_definition.metadata.display_name,
        ),
        schema=ConnectorConfigurationSchemaResponse(
            fields=configuration_fields_from_schema(connector_definition.configuration_schema)
        ),
        configuration=masked_configuration,
    )


@router.post("/{connector_id}/configuration/validations")
async def post_connector_configuration_check(
    connector_id: str,
    save_request: ConnectorConfigurationSaveRequest,
    dependencies: Annotated[
        ConnectorConfigurationSaveDependencies,
        Depends(get_connector_configuration_save_dependencies),
    ],
) -> ConnectorConfigurationCheckResult:
    connector_definition = dependencies.connector_registry.get_connector_definition(
        connector_id, ConnectorDefinitionFilter(availability="available")
    )
    if connector_definition is None:
        raise HTTPException(status_code=404, detail="Connector is not available for configuration")
    try:
        configuration = await validate_connector_configuration_input(
            connector_id=connector_id,
            schema=connector_definition.configuration_schema,
            store=dependencies.store,
            configuration=save_request.configuration,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_input=False)) from error
    return dependencies.connector_registry.check_configuration(connector_id, configuration)


@router.put("/{connector_id}/publication", response_model=None)
async def put_connector_publication(
    connector_id: str,
    dependencies: Annotated[
        ConnectorPublicationDependencies, Depends(get_connector_publication_dependencies)
    ],
) -> ConnectorPublicationResponse | JSONResponse:
    if (
        dependencies.connector_registry.get_connector_definition(
            connector_id, ConnectorDefinitionFilter(availability="available")
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Connector is not available for publication")
    validation_error = await _connector_publication_validation_error(dependencies, connector_id)
    if validation_error is not None:
        return validation_error
    await dependencies.publishing_store.publish_connector(connector_id)
    if dependencies.event_stream is not None:
        await dependencies.event_stream.append(
            connector_publication_changed_event(connector_id, "published")
        )
    return ConnectorPublicationResponse(connector_id=connector_id, publication_status="published")


@router.delete("/{connector_id}/publication")
async def delete_connector_publication(
    connector_id: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    publishing_store: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)],
    event_stream: Annotated[
        EventStream | None,
        Depends(get_connector_event_stream),
    ],
) -> ConnectorPublicationResponse:
    if (
        connector_registry.get_connector_definition(
            connector_id, ConnectorDefinitionFilter(availability="available")
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Connector is not available for publication")
    await publishing_store.unpublish_connector(connector_id)
    if event_stream is not None:
        await event_stream.append(connector_publication_changed_event(connector_id, "unpublished"))
    return ConnectorPublicationResponse(connector_id=connector_id, publication_status="unpublished")


@router.get("/{connector_id}/prompts")
async def list_connector_prompts(
    connector_id: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    activation_port: Annotated[ActivationPort, Depends(get_capability_activation_port)],
) -> ConnectorPromptListResponse:
    connector_definition = connector_registry.get_connector_definition(
        connector_id, ConnectorDefinitionFilter(availability="available")
    )
    if connector_definition is None:
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} was not found")
    activations = {
        state.ref.capability_key: state.activation_status
        for state in await activation_port.list_activations(
            connector_id, "prompt", ActivationListFilter()
        )
    }
    prompts = [
            ConnectorPromptResponse(
                name=prompt.name,
                description=prompt.description,
                arguments=[
                    ConnectorPromptArgumentResponse(
                        name=argument.name,
                        description=argument.description,
                        required=argument.required,
                    )
                    for argument in prompt.arguments
                ],
                activation_status=activations.get(prompt.name, ActivationStatus.DISABLED).value,
            )
            for prompt in connector_definition.prompt_descriptions
        ]
    return ConnectorPromptListResponse(
        prompts=prompts,
        available_actions=["activate"] if prompts else [],
    )


@router.put(
    "/{connector_id}/prompts/activation",
    response_model=ConnectorPromptActivationBatchResponse,
)
async def put_connector_prompt_activations(
    connector_id: str,
    request: ConnectorPromptActivationBatchRequest,
    activation_port: Annotated[ActivationPort, Depends(get_capability_activation_port)],
    event_stream: Annotated[
        EventStream | None,
        Depends(get_connector_event_stream),
    ],
) -> ConnectorPromptActivationBatchResponse:
    known = {
        state.ref.capability_key
        for state in await activation_port.list_activations(
            connector_id, "prompt", ActivationListFilter()
        )
    }
    if any(item.prompt_id not in known for item in request.prompts):
        raise HTTPException(status_code=404, detail="Connector prompt was not found")
    batch = await activation_port.set_statuses(
        tuple(
            CapabilityActivationState(
                ref=CapabilityRef(
                    connector_kind="native",
                    connector_id=connector_id,
                    capability_kind="prompt",
                    capability_key=item.prompt_id,
                ),
                activation_status=ActivationStatus(item.activation_status),
            )
            for item in request.prompts
        )
    )
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
    return ConnectorPromptActivationBatchResponse(
        connector_id=connector_id,
        prompts=[
            ConnectorPromptActivationBatchResponseItem(
                prompt_id=state.ref.capability_key,
                activation_status=state.activation_status.value,
            )
            for state in batch.states
        ],
    )


@router.get("/{connector_id}/resources")
async def list_connector_resources(
    connector_id: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    activation_port: Annotated[ActivationPort, Depends(get_capability_activation_port)],
) -> ConnectorResourceListResponse:
    connector_definition = connector_registry.get_connector_definition(
        connector_id, ConnectorDefinitionFilter(availability="available")
    )
    if connector_definition is None:
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} was not found")
    resource_activations = {
        state.ref.capability_key: state.activation_status
        for state in await activation_port.list_activations(
            connector_id, "resource", ActivationListFilter()
        )
    }
    template_activations = {
        state.ref.capability_key: state.activation_status
        for state in await activation_port.list_activations(
            connector_id, "resource_template", ActivationListFilter()
        )
    }
    resources = [
            ConnectorResourceResponse(
                kind=resource.kind,
                name=resource.name,
                description=resource.description,
                uri=resource.uri,
                activation_status=(
                    template_activations if resource.kind == "resource_template" else resource_activations
                )
                .get(resource.uri, ActivationStatus.DISABLED)
                .value,
            )
            for resource in connector_definition.resource_descriptions
        ]
    return ConnectorResourceListResponse(
        resources=resources,
        available_actions=["activate"] if resources else [],
    )


@router.put(
    "/{connector_id}/resources/activation",
    response_model=ConnectorResourceActivationBatchResponse,
)
async def put_connector_resource_activations(
    connector_id: str,
    request: ConnectorResourceActivationBatchRequest,
    activation_port: Annotated[ActivationPort, Depends(get_capability_activation_port)],
    event_stream: Annotated[
        EventStream | None,
        Depends(get_connector_event_stream),
    ],
) -> ConnectorResourceActivationBatchResponse:
    known = {
        ("resource", state.ref.capability_key)
        for state in await activation_port.list_activations(
            connector_id, "resource", ActivationListFilter()
        )
    } | {
        ("resource_template", state.ref.capability_key)
        for state in await activation_port.list_activations(
            connector_id, "resource_template", ActivationListFilter()
        )
    }
    if any((item.kind, item.resource_id) not in known for item in request.resources):
        raise HTTPException(status_code=404, detail="Connector resource was not found")
    batch = await activation_port.set_statuses(
        tuple(
            CapabilityActivationState(
                ref=CapabilityRef(
                    connector_kind="native",
                    connector_id=connector_id,
                    capability_kind=item.kind,
                    capability_key=item.resource_id,
                ),
                activation_status=ActivationStatus(item.activation_status),
            )
            for item in request.resources
        )
    )
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
    return ConnectorResourceActivationBatchResponse(
        connector_id=connector_id,
        resources=[
            ConnectorResourceActivationBatchResponseItem(
                resource_id=state.ref.capability_key,
                kind=state.ref.capability_kind,  # type: ignore[arg-type]
                activation_status=state.activation_status.value,
            )
            for state in batch.states
        ],
    )


@router.get("/{connector_id}/tools")
@router.get("/{connector_id}/tools/activation")
async def list_connector_tools(
    connector_id: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    activation_port: Annotated[
        ActivationPort, Depends(get_capability_activation_port)
    ],
    activation_status: Annotated[
        ActivationFilter, Depends(get_capability_activation_filter)
    ],
    policy_store: Annotated[
        ConnectorInvocationPolicyStore, Depends(get_connector_invocation_policy_store)
    ],
) -> ConnectorToolActivationListResponse:
    if (
        connector_registry.get_connector_definition(
            connector_id, ConnectorDefinitionFilter(availability="available")
        )
        is None
    ):
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} was not found")
    return await list_tool_activations(
        connector_kind="native",
        connector_id=connector_id,
        activation_port=activation_port,
        policy_store=policy_store,
        activation_filter=ActivationListFilter(activation_status=activation_status),
    )


@router.put(
    "/{connector_id}/tools/activation",
    response_model=ConnectorToolActivationListResponse,
    responses={409: {"model": ConnectorToolInvocationPolicyConflictResponse}},
)
async def put_connector_tool_activations(
    connector_id: str,
    request: ConnectorToolActivationBatchRequest,
    activation_port: Annotated[
        ActivationPort, Depends(get_capability_activation_port)
    ],
    mutation_port: Annotated[
        ConnectorToolConfigurationMutationPort,
        Depends(get_connector_tool_configuration_mutation_port),
    ],
    event_stream: Annotated[
        EventStream | None,
        Depends(get_connector_event_stream),
    ],
) -> ConnectorToolActivationListResponse | JSONResponse:
    catalog_tools = await activation_port.list_activations(connector_id, "tool", ActivationListFilter())
    return await put_tool_activations(
        connector_kind="native",
        connector_id=connector_id,
        items=request.tools,
        known_operation_names=tuple(tool.ref.capability_key for tool in catalog_tools),
        mutation_port=mutation_port,
        event_stream=event_stream,
        activation_event_policy=AlwaysPublishActivationEvents(),
    )


@router.get("/{connector_id}")
async def get_connector_detail(
    connector_id: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    presentation_service: Annotated[
        ConnectorPresentationService, Depends(get_connector_presentation_service)
    ],
) -> ConnectorDetailResponse:
    connector_definition = connector_registry.get_connector_definition(
        connector_id, ConnectorDefinitionFilter(availability="registered")
    )
    if connector_definition is None:
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} was not found")
    if not connector_definition.available:
        raise HTTPException(
            status_code=404,
            detail=f"Connector {connector_id} is registered but not available in this deployment",
        )
    return await presentation_service.detail(connector_definition)


@router.put(
    "/{connector_id}/configuration",
    response_model=ConnectorConfigurationSaveResponse,
)
async def put_connector_configuration(
    connector_id: str,
    save_request: ConnectorConfigurationSaveRequest,
    dependencies: Annotated[
        ConnectorConfigurationSaveDependencies,
        Depends(get_connector_configuration_save_dependencies),
    ],
) -> ConnectorConfigurationSaveResponse:
    connector_definition = dependencies.connector_registry.get_connector_definition(
        connector_id, ConnectorDefinitionFilter(availability="available")
    )
    if connector_definition is None:
        raise HTTPException(status_code=404, detail="Connector is not available for configuration")
    try:
        configuration = await save_connector_configuration(
            connector_id=connector_id,
            schema=connector_definition.configuration_schema,
            store=dependencies.store,
            configuration=save_request.configuration,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_input=False)) from error
    if dependencies.event_stream is not None:
        await dependencies.event_stream.append(connector_configuration_changed_event(connector_id))
    masked_configuration = masked_configuration_dump(configuration)
    return ConnectorConfigurationSaveResponse(
        connector_id=connector_id,
        status="configured",
        configuration=masked_configuration or {},
    )


async def _connector_publication_validation_error(
    dependencies: ConnectorPublicationDependencies, connector_id: str
) -> JSONResponse | None:
    configuration = await dependencies.configuration_store.get_current_configuration(connector_id)
    if configuration is None:
        return JSONResponse(
            status_code=422,
            content={"message": "Connector configuration must be valid before publishing"},
        )
    check_result = dependencies.connector_registry.check_configuration(connector_id, configuration)
    if not check_result.valid:
        return JSONResponse(
            status_code=422,
            content=check_result.model_dump(exclude_none=True),
        )
    return None
