from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from umbod.core.capabilities.descriptions import (
    CapabilityDescriptionOverrideResolver,
    CapabilityDescriptionTargetNotFoundError,
    ClearCapabilityDescriptionOverride,
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    ConnectorKind,
    ConnectorKindMismatchError,
    OverrideRevisionConflictError,
    OverriddenCapabilityDescription,
    SetCapabilityDescriptionOverride,
)
from umbod.core.capabilities.descriptions.events import connector_capability_description_override_changed_event
from umbod.rest.capability_descriptions.dependencies import (
    get_override_store,
    get_resolver,
)
from umbod.rest.capability_descriptions.schemas import (
    CapabilityDescriptionResponse,
    OverriddenOverrideResponse,
    OverrideRequest,
    OverrideResponse,
    RevisionConflictResponse,
    SetOverrideRequest,
    SystemOverrideResponse,
)
from umbod.rest.connectors.dependencies import get_connector_event_stream
from messaging.ports import EventStream

router = APIRouter(
    prefix="/connector-capability-descriptions", tags=["connector-capability-descriptions"]
)
Resolver = Annotated[CapabilityDescriptionOverrideResolver, Depends(get_resolver)]
Store = Annotated[ConnectorCapabilityDescriptionOverrideStore, Depends(get_override_store)]


@router.get("/{connector_kind}/{connector_id}")
async def get_capability_description(
    connector_kind: ConnectorKind,
    connector_id: str,
    resolver: Resolver,
    store: Store,
) -> CapabilityDescriptionResponse:
    return await _response(
        ConnectorCapabilityDescriptionKey(kind=connector_kind, connector_id=connector_id),
        resolver,
        store,
    )


@router.put("/{connector_kind}/{connector_id}")
async def put_capability_description(
    connector_kind: ConnectorKind,
    connector_id: str,
    request: OverrideRequest,
    resolver: Resolver,
    store: Store,
    event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)],
) -> CapabilityDescriptionResponse:
    key = ConnectorCapabilityDescriptionKey(kind=connector_kind, connector_id=connector_id)
    try:
        if isinstance(request, SetOverrideRequest):
            changed = await resolver.set(
                SetCapabilityDescriptionOverride(
                    key=key,
                    description=request.description,
                    expected_revision=request.expected_revision,
                )
            )
        else:
            changed = await resolver.clear(
                ClearCapabilityDescriptionOverride(
                    key=key, expected_revision=request.expected_revision
                )
            )
        response = await _response(key, resolver, store)
        if event_stream is not None:
            await event_stream.append(
                connector_capability_description_override_changed_event(
                    connector_kind,
                    connector_id,
                    request.action,
                    changed.revision,
                )
            )
        return response
    except OverrideRevisionConflictError as error:
        current = await _response(key, resolver, store)
        raise HTTPException(
            status_code=409,
            detail=RevisionConflictResponse(
                code="capability_description_revision_conflict", current=current
            ).model_dump(),
        ) from error
    except (CapabilityDescriptionTargetNotFoundError, ConnectorKindMismatchError) as error:
        raise HTTPException(status_code=404, detail="Connector not found") from error


async def _response(
    key: ConnectorCapabilityDescriptionKey,
    resolver: CapabilityDescriptionOverrideResolver,
    store: ConnectorCapabilityDescriptionOverrideStore,
) -> CapabilityDescriptionResponse:
    try:
        effective = await resolver.resolve(key)
        state = await store.get(key)
        override: OverrideResponse
        if isinstance(state, OverriddenCapabilityDescription):
            override = OverriddenOverrideResponse(
                state="overridden", description=state.description, revision=state.revision
            )
        else:
            override = SystemOverrideResponse(state="system", revision=state.revision)
        base = await resolver.base_description(key)
        return CapabilityDescriptionResponse(
            connector_kind=key.kind,
            connector_id=key.connector_id,
            base_description=base,
            effective_description=effective.description,
            override=override,
        )
    except (CapabilityDescriptionTargetNotFoundError, ConnectorKindMismatchError) as error:
        raise HTTPException(status_code=404, detail="Connector not found") from error
