"""Shared administration contract for downstream OAuth, including native clients."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
)
from umbod.rest.connectors.downstream_mcp.dependencies import get_definition_store

router = APIRouter(prefix="/connectors/mcp/oauth", tags=["Downstream MCP OAuth"])


class BeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(default="", max_length=4096)
    scopes: str | None = Field(default=None, max_length=8192)


class Diagnostic(BaseModel):
    time: int
    stage: str
    result: Literal["started", "failed"]


class OAuthDetails(BaseModel):
    status: str
    error: str | None
    callback_url: str
    has_authorization: bool
    has_refresh_token: bool
    granted_scopes: str | None
    requested_scopes: str
    available_scopes: list[str]
    registration: Literal["unknown", "manual", "automatic", "hosted_metadata"]
    stage: str
    diagnostics: list[Diagnostic]
    canonical_endpoint: str | None = None
    endpoint_differs: bool | None = None
    issuer: str | None = None


def get_oauth_service() -> OAuthService:
    # Deployment composition overrides this dependency only when callback routing
    # and credential ownership are configured for the worker lifecycle.
    raise HTTPException(503, detail={"code": "oauth_host_unavailable"})


Service = Annotated[OAuthService, Depends(get_oauth_service)]


async def get_connector_oauth_service(
    connector_id: str,
    service: Service,
    definitions: Annotated[ConnectorDefinitionStore, Depends(get_definition_store)],
) -> OAuthService:
    result = await definitions.get(ConnectorIdQuery(connector_id=connector_id))
    if isinstance(result, ConnectorDefinitionFound) and uses_personal_oauth(result.definition):
        raise HTTPException(409, detail={"code": "personal_oauth_unavailable"})
    return service


ConnectorService = Annotated[OAuthService, Depends(get_connector_oauth_service)]


@router.get("/status")
async def status(service: Service):
    return {
        "oauth_status": service.results,
        "oauth_errors": service.errors,
        "oauth_stages": service.stages,
    }


async def execute(
    service: OAuthService, connector_id: str, operation: str, **kwargs: object
) -> object:
    try:
        key = service.host.resolve(connector_id)
        result = await getattr(service, operation)(key, **kwargs)
        return result if result is not None else {"status": "signed_out"}
    except KeyError:
        raise HTTPException(404, "Connector not found") from None
    except Exception as exc:
        raise HTTPException(422, service.failure_message(exc)) from None


@router.get("/{connector_id}", response_model=OAuthDetails)
async def details(connector_id: str, service: ConnectorService) -> object:
    return await execute(service, connector_id, "details")


@router.post("/{connector_id}/discover", response_model=OAuthDetails)
async def discover(connector_id: str, service: ConnectorService) -> object:
    return await execute(service, connector_id, "discover")


@router.post("/{connector_id}/begin")
async def begin(connector_id: str, body: BeginRequest, service: ConnectorService) -> object:
    return await execute(service, connector_id, "begin", **body.model_dump())


@router.post("/{connector_id}/cancel")
async def cancel(connector_id: str, service: ConnectorService) -> object:
    return await execute(service, connector_id, "cancel")


@router.post("/{connector_id}/refresh")
async def refresh(connector_id: str, service: ConnectorService) -> object:
    return await execute(service, connector_id, "refresh")


@router.post("/{connector_id}/logout")
async def logout(connector_id: str, service: ConnectorService) -> object:
    return await execute(service, connector_id, "logout")
