from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from messaging.ports import EventStream
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    SetCapabilityDescriptionOverride,
)
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.invocation import (
    ConnectorInvocationPolicyStore,
)
from umbod.core.invocation.tools.configuration import AlwaysPublishActivationEvents
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolConfigurationMutationPort
from umbod.core.activation import (
    ActivationPort,
)
from umbod.core.connectors.openapi.errors import (
    OpenApiCandidateValidationError,
    OpenApiPermissionGrantConflict,
)
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import (
    CreateOpenApiConnector,
    ImportOpenApiCatalog,
    OpenApiConfigurationPort,
    OpenApiConnector,
    OpenApiConnectorCatalog,
    OpenApiConnectorManagementService,
)
from umbod.core.connectors.openapi.stores import CurrentOpenApiCatalogHeaderReader
from umbod.core.connectors.openapi.catalog import (
    OpenApiConnectorToolCatalog,
    OpenApiOperationTool,
)
from umbod.rest.connectors.capability_description import capability_description_fields
from umbod.rest.connectors.dependencies import (
    get_connector_event_stream,
    get_connector_invocation_policy_store,
    get_connector_publishing_store,
    get_connector_tool_configuration_mutation_port,
)
from umbod.rest.connectors.publication import openapi_available_actions, resolve_publication_status
from umbod.rest.connectors.schemas import (
    ConnectorToolInvocationPolicyConflictResponse,
    OverriddenInitialCapabilityDescriptionOverride,
)
from umbod.rest.connectors.tool_activation import list_tool_activations, put_tool_activations
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.connectors.openapi.dependencies import (
    get_openapi_candidate_importer,
    get_openapi_configuration_port,
    get_openapi_connector_management_service,
    get_openapi_connector_store,
    get_openapi_json_import_max_bytes,
    get_openapi_tool_activation_port,
    get_openapi_tool_catalog,
)
from umbod.rest.connectors.openapi.file_import import (
    decode_json_request_object,
    read_json_object,
)
from umbod.rest.connectors.openapi.schemas import (
    CreateOpenApiConnectorRequest,
    ImportOpenApiCatalogRequest,
    OpenApiCatalogImportResponse,
    OpenApiConfigurationRequest,
    OpenApiConfigurationResponse,
    OpenApiConnectorListResponse,
    OpenApiConnectorResponse,
    OpenApiConnectorSummaryResponse,
    OpenApiOperationToolListResponse,
    OpenApiOperationToolResponse,
    OpenApiOperationToolWithoutOutputSchemaResponse,
    OpenApiOperationToolWithOutputSchemaResponse,
    OpenApiPublicationResponse,
    OpenApiToolActivationBatchRequest,
    OpenApiToolActivationBatchResponse,
)

router = APIRouter(prefix="/connectors/openapi", tags=["openapi-connectors"])
Service = Annotated[
    OpenApiConnectorManagementService, Depends(get_openapi_connector_management_service)
]
Importer = Annotated[InMemoryOpenApiCandidateImporter, Depends(get_openapi_candidate_importer)]
JsonImportMaxBytes = Annotated[int, Depends(get_openapi_json_import_max_bytes)]
ToolCatalog = Annotated[OpenApiConnectorToolCatalog, Depends(get_openapi_tool_catalog)]
ActivationPort = Annotated[ActivationPort, Depends(get_openapi_tool_activation_port)]
PublishingStore = Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)]
CatalogReader = Annotated[CurrentOpenApiCatalogHeaderReader, Depends(get_openapi_connector_store)]
PolicyStore = Annotated[
    ConnectorInvocationPolicyStore, Depends(get_connector_invocation_policy_store)
]
ToolConfigurationMutation = Annotated[
    ConnectorToolConfigurationMutationPort,
    Depends(get_connector_tool_configuration_mutation_port),
]
ConnectorEventStream = Annotated[EventStream | None, Depends(get_connector_event_stream)]


async def get_capability_description_override_store(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorCapabilityDescriptionOverrideStore:
    return await factories.connector_capability_description_override_store.create()


ConfigurationPort = Annotated[OpenApiConfigurationPort, Depends(get_openapi_configuration_port)]
OverrideStore = Annotated[
    ConnectorCapabilityDescriptionOverrideStore, Depends(get_capability_description_override_store)
]


def _permission_conflict_http(error: OpenApiPermissionGrantConflict) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "openapi_operation_grants_conflict",
            "connector_id": error.connector_id,
            "removed_operation_ids": error.removed_operation_ids,
            "affected_group_ids": error.affected_group_ids,
        },
    )


async def _connector_response(
    connector: OpenApiConnector,
    publishing_store: ConnectorPublishingStore,
    catalog_reader: CurrentOpenApiCatalogHeaderReader,
    configured_connector_ids: frozenset[str],
    override_store: ConnectorCapabilityDescriptionOverrideStore,
) -> OpenApiConnectorResponse:
    description_fields = await capability_description_fields(
        connector_kind="openapi",
        connector_id=connector.connector_id,
        base_description=connector.capability_description,
        override_store=override_store,
    )
    status = await resolve_publication_status(
        connector_id=connector.connector_id,
        publishing_store=publishing_store,
        is_configured=connector.connector_id in configured_connector_ids,
    )
    return OpenApiConnectorResponse(
        connector_id=connector.connector_id,
        display_name=connector.display_name,
        tool_name_prefix=connector.tool_name_prefix,
        created_at=connector.created_at,
        updated_at=connector.updated_at,
        publication_status=status,
        available_actions=openapi_available_actions(status),
        **description_fields,
    )


@router.post("", response_model=OpenApiConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    request: CreateOpenApiConnectorRequest,
    service: Service,
    publishing_store: PublishingStore,
    catalog_reader: CatalogReader,
    override_store: OverrideStore,
) -> OpenApiConnectorResponse:
    try:
        connector = await service.create_connector(
            CreateOpenApiConnector(
                display_name=request.display_name,
                tool_name_prefix=request.tool_name_prefix,
                capability_description=request.capability_description,
            )
        )
        try:
            if isinstance(
                request.capability_description_override,
                OverriddenInitialCapabilityDescriptionOverride,
            ):
                await override_store.set(
                    SetCapabilityDescriptionOverride(
                        key=ConnectorCapabilityDescriptionKey(
                            kind="openapi", connector_id=connector.connector_id
                        ),
                        description=request.capability_description_override.description,
                        expected_revision=0,
                    )
                )
        except Exception:
            await service.delete_connector(connector.connector_id)
            raise
        return await _connector_response(
            connector,
            publishing_store,
            catalog_reader,
            await catalog_reader.current_catalog_connector_ids((connector.connector_id,)),
            override_store,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"message": str(error)}) from error


@router.get("", response_model=OpenApiConnectorListResponse)
async def list_connectors(
    service: Service,
    publishing_store: PublishingStore,
    catalog_reader: CatalogReader,
    override_store: OverrideStore,
) -> OpenApiConnectorListResponse:
    connectors = await service.list_connectors()
    configured_connector_ids = await catalog_reader.current_catalog_connector_ids(
        tuple(connector.connector_id for connector in connectors)
    )
    summaries = []
    for connector in connectors:
        publication_status = await resolve_publication_status(
            connector_id=connector.connector_id,
            publishing_store=publishing_store,
            is_configured=connector.connector_id in configured_connector_ids,
        )
        summaries.append(
            OpenApiConnectorSummaryResponse(
                connector_id=connector.connector_id,
                display_name=connector.display_name,
                publication_status=publication_status,
                available_actions=openapi_available_actions(publication_status),
            )
        )
    return OpenApiConnectorListResponse(connectors=tuple(summaries))


@router.get("/{connector_id}", response_model=OpenApiConnectorResponse)
async def get_connector(
    connector_id: str,
    service: Service,
    publishing_store: PublishingStore,
    catalog_reader: CatalogReader,
    override_store: OverrideStore,
) -> OpenApiConnectorResponse:
    try:
        return await _connector_response(
            await service.get_connector(connector_id),
            publishing_store,
            catalog_reader,
            await catalog_reader.current_catalog_connector_ids((connector_id,)),
            override_store,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: str, service: Service, override_store: OverrideStore
) -> None:
    try:
        await service.delete_connector(connector_id)
        await override_store.delete(
            ConnectorCapabilityDescriptionKey(kind="openapi", connector_id=connector_id)
        )
    except KeyError:
        await override_store.delete(
            ConnectorCapabilityDescriptionKey(kind="openapi", connector_id=connector_id)
        )


def _configuration_response(
    configured: bool, authentication_type: Literal["none", "bearer"]
) -> OpenApiConfigurationResponse:
    return OpenApiConfigurationResponse(
        configured=configured,
        authentication_type=authentication_type,
        masked_token="********" if configured else None,
    )


@router.get("/{connector_id}/configuration", response_model=OpenApiConfigurationResponse)
async def get_configuration(
    connector_id: str, service: Service, configuration: ConfigurationPort
) -> OpenApiConfigurationResponse:
    try:
        await service.get_connector(connector_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error
    current = await configuration.status(connector_id)
    return _configuration_response(current.configured, current.authentication_type)


@router.put("/{connector_id}/configuration", response_model=OpenApiConfigurationResponse)
async def put_configuration(
    connector_id: str,
    request: OpenApiConfigurationRequest,
    service: Service,
    configuration: ConfigurationPort,
) -> OpenApiConfigurationResponse:
    try:
        await service.get_connector(connector_id)
        result = await (
            configuration.clear(connector_id)
            if request.authentication_type == "none"
            else configuration.configure(connector_id, request.bearer_token)
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid connector configuration") from error
    return _configuration_response(result.configured, result.authentication_type)


def _catalog_import_response(catalog: OpenApiConnectorCatalog) -> OpenApiCatalogImportResponse:
    return OpenApiCatalogImportResponse(
        connector_id=catalog.connector_id,
        catalog_id=catalog.catalog_id,
        operation_ids=catalog.operation_ids,
        approved_hosts=catalog.approved_hosts,
        selected_server_url=catalog.selected_server_url,
        imported_at=catalog.imported_at,
    )


@router.post(
    "/{connector_id}/imports",
    response_model=OpenApiCatalogImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_catalog(
    connector_id: str,
    request: Request,
    service: Service,
    importer: Importer,
    max_bytes: JsonImportMaxBytes,
) -> OpenApiCatalogImportResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        content = await request.body()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413, detail={"code": "openapi_import_too_large", "max_bytes": max_bytes}
            )
        decoded_request = decode_json_request_object(content)
        try:
            request_dto = ImportOpenApiCatalogRequest.model_validate(decoded_request)
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "openapi_import_invalid_request",
                    "message": str(error.errors(include_input=False)[0]["msg"]),
                },
            ) from error
        document = request_dto.document
        approved_hosts = request_dto.approved_hosts
    elif content_type == "multipart/form-data":
        form = await request.form()
        file = form.get("file")
        document = await read_json_object(
            file if isinstance(file, StarletteUploadFile) else "", max_bytes
        )
        approved_hosts = tuple(str(value) for value in form.getlist("approved_hosts"))
    else:
        raise HTTPException(
            status_code=415, detail={"code": "openapi_import_unsupported_media_type"}
        )
    try:
        await service.get_connector(connector_id)
        candidate = importer.import_candidate(document)
        catalog = await service.import_catalog(
            ImportOpenApiCatalog(
                connector_id=connector_id,
                source_document=document,
                candidate=candidate,
                approved_hosts=approved_hosts,
            )
        )
        return _catalog_import_response(catalog)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error
    except OpenApiPermissionGrantConflict as error:
        raise _permission_conflict_http(error) from error
    except OpenApiCandidateValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={"issues": [issue.model_dump(mode="json") for issue in error.issues]},
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"message": str(error)}) from error


def _operation_tool_response(tool: OpenApiOperationTool) -> OpenApiOperationToolResponse:
    values = {
        "operation_id": tool.operation_id,
        "method": tool.method,
        "path": tool.path,
        "summary": tool.summary,
        "description": tool.description,
        "activation_status": tool.activation_status,
        "parameters": tool.parameters,
    }
    if tool.output_schema.output_schema_status == "present":
        return OpenApiOperationToolWithOutputSchemaResponse(
            **values, output_schema=tool.output_schema.output_schema
        )
    return OpenApiOperationToolWithoutOutputSchemaResponse(**values)


@router.get("/{connector_id}/tools", response_model=OpenApiOperationToolListResponse)
async def list_tools(
    connector_id: str, service: Service, catalog: ToolCatalog
) -> OpenApiOperationToolListResponse:
    try:
        await service.get_connector(connector_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error
    return OpenApiOperationToolListResponse(
        tools=[
            _operation_tool_response(tool)
            for tool in await catalog.list_operation_tools(connector_id)
        ]
    )


@router.get(
    "/{connector_id}/tools/activation",
    response_model=OpenApiToolActivationBatchResponse,
)
async def get_tool_activations(
    connector_id: str,
    service: Service,
    activation: ActivationPort,
    policy_store: PolicyStore,
) -> OpenApiToolActivationBatchResponse:
    try:
        await service.get_connector(connector_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error
    return await list_tool_activations(
        connector_kind="openapi",
        connector_id=connector_id,
        activation_port=activation,
        policy_store=policy_store,
    )


@router.put(
    "/{connector_id}/tools/activation",
    response_model=OpenApiToolActivationBatchResponse,
    responses={409: {"model": ConnectorToolInvocationPolicyConflictResponse}},
)
async def set_tool_activations(
    connector_id: str,
    request: OpenApiToolActivationBatchRequest,
    activation: ActivationPort,
    catalog: ToolCatalog,
    mutation_port: ToolConfigurationMutation,
    event_stream: ConnectorEventStream,
) -> OpenApiToolActivationBatchResponse | JSONResponse:
    catalog_tools = await catalog.list_operation_tools(connector_id)
    return await put_tool_activations(
        connector_kind="openapi",
        connector_id=connector_id,
        items=request.tools,
        known_operation_names=tuple(tool.operation_id for tool in catalog_tools),
        mutation_port=mutation_port,
        event_stream=event_stream,
        activation_event_policy=AlwaysPublishActivationEvents(),
    )


@router.put("/{connector_id}/publication", response_model=OpenApiPublicationResponse)
async def publish_connector(
    connector_id: str,
    service: Service,
    publishing_store: PublishingStore,
    catalog_reader: CatalogReader,
) -> OpenApiPublicationResponse:
    try:
        await service.get_connector(connector_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error
    if not await catalog_reader.current_catalog_exists(connector_id):
        raise HTTPException(status_code=409, detail="Import an OpenAPI catalog before publication")
    if not await publishing_store.is_published(connector_id):
        await publishing_store.publish_connector(connector_id)
    return OpenApiPublicationResponse(connector_id=connector_id, publication_status="published")


@router.delete("/{connector_id}/publication", response_model=OpenApiPublicationResponse)
async def unpublish_connector(
    connector_id: str,
    service: Service,
    publishing_store: PublishingStore,
) -> OpenApiPublicationResponse:
    try:
        await service.get_connector(connector_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="OpenAPI connector not found") from error
    if await publishing_store.is_published(connector_id):
        await publishing_store.unpublish_connector(connector_id)
    return OpenApiPublicationResponse(connector_id=connector_id, publication_status="unpublished")
