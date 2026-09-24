from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from messaging.models import StreamEvent
from messaging.ports import EventStream

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.activation import ActivationStore, CapabilityRef

from umbod.rest.mcp_permissions.dependencies import get_group_permission_store
from umbod.rest.mcp_permissions.mappers import group_permission_response
from umbod.rest.mcp_permissions.schemas import GroupPermissionDetailListResponse
from umbod.rest.system.dependencies import (
    get_connector_current_configuration_store,
    get_connector_publishing_store,
    get_connector_registry,
    get_capability_activation_store,
    get_event_stream,
)
from umbod.rest.system.runtime_state import (
    ConnectorRuntimeStateService,
    RawConnectorConfigurationSerializer,
)
from umbod.rest.system.schemas import (
    ConnectorRuntimeStateResponse,
    ConnectorToolRuntimeStateResponse,
    EventListQuery,
    HealthResponse,
)
from umbod.core.permissions import GroupPermissionStore


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="umbod-api")


@router.get("/events")
async def list_events(
    query: Annotated[EventListQuery, Query()],
    event_stream: Annotated[EventStream | None, Depends(get_event_stream)],
) -> list[StreamEvent]:
    if event_stream is None:
        return []
    return await event_stream.list_after_types(
        query.after_sequence,
        query.limit,
        () if query.event_type is None else query.event_type,
    )


@router.get("/mcp-permissions/groups")
async def list_runtime_group_permissions(
    store: Annotated[GroupPermissionStore, Depends(get_group_permission_store)],
) -> GroupPermissionDetailListResponse:
    return GroupPermissionDetailListResponse(
        groups=[
            group_permission_response(permission_set)
            for permission_set in await store.list_all_group_permissions()
        ]
    )


@router.get("/connectors/runtime-state")
async def list_connector_runtime_states(
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    configuration_store: Annotated[
        ConnectorCurrentConfigurationStore,
        Depends(get_connector_current_configuration_store),
    ],
    publishing_store: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)],
) -> list[ConnectorRuntimeStateResponse]:
    runtime_state_service = ConnectorRuntimeStateService(
        connector_registry,
        configuration_store,
        publishing_store,
        RawConnectorConfigurationSerializer(),
    )
    return [
        await runtime_state_service.get_runtime_state(connector_definition.metadata.id)
        for connector_definition in connector_registry.list_connector_definitions(
            ConnectorDefinitionFilter(availability="registered")
        )
    ]


@router.get("/connectors/{connector_id}/tool/{operation_name}")
async def get_connector_tool_runtime_state(
    connector_id: str,
    operation_name: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    activation_store: Annotated[
        ActivationStore, Depends(get_capability_activation_store)
    ],
) -> ConnectorToolRuntimeStateResponse:
    connector_definition = connector_registry.get_connector_definition(
        connector_id, ConnectorDefinitionFilter(availability="available")
    )
    if connector_definition is None or operation_name not in connector_definition.tool_descriptions:
        raise HTTPException(status_code=404, detail="Connector tool runtime state was not found")
    status = await activation_store.get_status(
        CapabilityRef(
            connector_kind="native",
            connector_id=connector_id,
            capability_kind="tool",
            capability_key=operation_name,
        )
    )
    return ConnectorToolRuntimeStateResponse(
        connector_id=connector_id,
        operation_name=operation_name,
        status=status.value,
    )


@router.get("/connectors/{connector_id}/runtime-state")
async def get_connector_runtime_state(
    connector_id: str,
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    configuration_store: Annotated[
        ConnectorCurrentConfigurationStore,
        Depends(get_connector_current_configuration_store),
    ],
    publishing_store: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)],
) -> ConnectorRuntimeStateResponse:
    if (
        connector_registry.get_connector_definition(
            connector_id, ConnectorDefinitionFilter(availability="registered")
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Connector runtime state was not found")
    runtime_state_service = ConnectorRuntimeStateService(
        connector_registry,
        configuration_store,
        publishing_store,
        RawConnectorConfigurationSerializer(),
    )
    return await runtime_state_service.get_runtime_state(connector_id)
