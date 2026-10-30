from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from pydantic import BaseModel, ConfigDict, Field

from umbod.core.identity_directory.models import (
    DirectoryScope,
    GroupPage,
    IdentityObservation,
    UserPage,
)
from umbod.core.identity_directory.ports import IdentityDirectoryStore
from umbod.core.identity_directory.service import IdentityObservationService
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from .deps import capture_observation, get_identity_directory, get_observation_service

personal_router = APIRouter()
admin_router = APIRouter(prefix="/identity-directory")


@personal_router.post("/identity-observations", status_code=204)
async def observe_identity(
    request: Request,
    background_tasks: BackgroundTasks,
    observation: Annotated[Optional[IdentityObservation], Depends(capture_observation)],
    service: Annotated[IdentityObservationService, Depends(get_observation_service)],
) -> Response:
    if await request.body():
        raise HTTPException(status_code=422, detail="Request body is not allowed")
    if observation is not None:
        background_tasks.add_task(service.observe_best_effort, observation)
    return Response(status_code=204)


class DirectoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=50, ge=1, le=100)


def directory_scope(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
    search: Annotated[DirectoryQuery, Query()],
) -> DirectoryScope:
    return DirectoryScope(
        issuer=factories.settings.oidc.issuer_url,
        claim=factories.settings.mcp.permission_group_claim,
        query=search.query,
        limit=search.limit,
    )


@admin_router.get("/groups", response_model=GroupPage)
async def search_groups(
    scope: Annotated[DirectoryScope, Depends(directory_scope)],
    store: Annotated[IdentityDirectoryStore, Depends(get_identity_directory)],
) -> GroupPage:
    return await store.search_groups(scope)


@admin_router.get("/users", response_model=UserPage)
async def search_users(
    scope: Annotated[DirectoryScope, Depends(directory_scope)],
    store: Annotated[IdentityDirectoryStore, Depends(get_identity_directory)],
) -> UserPage:
    return await store.search_users(scope)
