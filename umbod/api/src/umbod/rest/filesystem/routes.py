from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import FilesystemCreation
from umbod.core.filesystem.browsing import Breadcrumbs, FilesystemBrowsing, NodeSummary
from umbod.core.filesystem.content import FilesystemContent

from .deps import (
    get_filesystem_browsing, get_filesystem_caller, get_filesystem_creation,
    get_filesystem_content,
)
from .deletion import router as deletion_router
from .downloads import DOWNLOAD_RESPONSES, download_response
from .errors import filesystem_errors
from .models import ChildrenResponse, CreateNodeRequest
from .planned.routes import router as planned_router
from .uploads import router as uploads_router
from .sharing import router as sharing_router

router = APIRouter(prefix="/filesystem", tags=["filesystem"])

Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Browsing = Annotated[FilesystemBrowsing, Depends(get_filesystem_browsing)]
Creation = Annotated[FilesystemCreation, Depends(get_filesystem_creation)]
Content = Annotated[FilesystemContent, Depends(get_filesystem_content)]


@router.get("/root", response_model=NodeSummary)
async def get_root(caller: Caller, browsing: Browsing) -> NodeSummary:
    with filesystem_errors():
        return await browsing.get_root(caller)


@router.get("/nodes/{node_id}", response_model=NodeSummary)
async def get_node(node_id: UUID, caller: Caller, browsing: Browsing, response: Response) -> NodeSummary:
    with filesystem_errors():
        node = await browsing.get_node(caller, node_id)
    response.headers["ETag"] = f'"{node.revision}"'
    return node


@router.get("/nodes/{node_id}/breadcrumbs", response_model=Breadcrumbs)
async def get_breadcrumbs(node_id: UUID, caller: Caller, browsing: Browsing) -> Breadcrumbs:
    with filesystem_errors():
        return await browsing.get_breadcrumbs(caller, node_id)


@router.get("/nodes/{parent_id}/children", response_model=ChildrenResponse)
async def list_children(parent_id: UUID, caller: Caller, browsing: Browsing) -> ChildrenResponse:
    with filesystem_errors():
        return ChildrenResponse(nodes=list(await browsing.list_children(caller, parent_id)))


@router.get(
    "/nodes/{node_id}/content", response_class=StreamingResponse, responses=DOWNLOAD_RESPONSES,
)
async def get_content(node_id: UUID, caller: Caller, content: Content) -> StreamingResponse:
    with filesystem_errors():
        download = await content.open_download(caller, node_id)
    return await download_response(download)


@router.post("/nodes/{parent_id}/directories", response_model=NodeSummary, status_code=201)
async def create_directory(
    parent_id: UUID, body: CreateNodeRequest, caller: Caller, creation: Creation,
) -> NodeSummary:
    with filesystem_errors():
        return await creation.create_directory(caller, parent_id, body.name, body.metadata.to_core_metadata())


router.include_router(sharing_router)
router.include_router(deletion_router)
router.include_router(planned_router)
router.include_router(uploads_router)
