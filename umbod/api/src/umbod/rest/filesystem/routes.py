from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import FilesystemCreation
from umbod.core.filesystem.browsing import FilesystemBrowsing, NodeSummary

from .deps import get_filesystem_browsing, get_filesystem_caller, get_filesystem_creation
from .errors import filesystem_errors
from .models import ChildrenResponse, CreateNodeRequest
from .planned.routes import router as planned_router
from .planned.uploads import FILE_CREATION_CONTRACT, FILE_CREATION_RESPONSES, parse_file_creation

router = APIRouter(prefix="/filesystem", tags=["filesystem"])

Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Browsing = Annotated[FilesystemBrowsing, Depends(get_filesystem_browsing)]
Creation = Annotated[FilesystemCreation, Depends(get_filesystem_creation)]


@router.get("/root", response_model=NodeSummary)
async def get_root(caller: Caller, browsing: Browsing) -> NodeSummary:
    with filesystem_errors():
        return await browsing.get_root(caller)


@router.get("/nodes/{node_id}", response_model=NodeSummary)
async def get_node(node_id: UUID, caller: Caller, browsing: Browsing) -> NodeSummary:
    with filesystem_errors():
        return await browsing.get_node(caller, node_id)


@router.get("/nodes/{parent_id}/children", response_model=ChildrenResponse)
async def list_children(parent_id: UUID, caller: Caller, browsing: Browsing) -> ChildrenResponse:
    with filesystem_errors():
        return ChildrenResponse(nodes=list(await browsing.list_children(caller, parent_id)))


@router.post(
    "/nodes/{parent_id}/files", response_model=NodeSummary, status_code=201,
    responses=FILE_CREATION_RESPONSES, openapi_extra=FILE_CREATION_CONTRACT,
)
async def create_file(
    parent_id: UUID, body: Annotated[CreateNodeRequest, Depends(parse_file_creation)],
    caller: Caller, creation: Creation,
) -> NodeSummary:
    with filesystem_errors():
        return await creation.create_file(caller, parent_id, body.name, body.metadata.to_core_metadata())


@router.post("/nodes/{parent_id}/directories", response_model=NodeSummary, status_code=201)
async def create_directory(
    parent_id: UUID, body: CreateNodeRequest, caller: Caller, creation: Creation,
) -> NodeSummary:
    with filesystem_errors():
        return await creation.create_directory(caller, parent_id, body.name, body.metadata.to_core_metadata())


router.include_router(planned_router)
