from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import FilesystemCreation
from umbod.core.filesystem.browsing import FilesystemBrowsing, NodeSummary
from umbod.core.filesystem.content import FilesystemContent

from .deps import (
    get_filesystem_browsing, get_filesystem_caller, get_filesystem_creation,
    get_filesystem_content, get_filesystem_upload_limit, require_filesystem_identity,
)
from .downloads import DOWNLOAD_RESPONSES, download_response
from .errors import filesystem_errors
from .models import ChildrenResponse, CreateNodeRequest, UploadPolicy
from .planned.routes import router as planned_router
from .uploads import UPLOAD_CONTRACT, UPLOAD_RESPONSES, upload_file

router = APIRouter(prefix="/filesystem", tags=["filesystem"])

Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Browsing = Annotated[FilesystemBrowsing, Depends(get_filesystem_browsing)]
Creation = Annotated[FilesystemCreation, Depends(get_filesystem_creation)]
Content = Annotated[FilesystemContent, Depends(get_filesystem_content)]
UploadLimit = Annotated[int, Depends(get_filesystem_upload_limit)]


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


@router.get(
    "/nodes/{parent_id}/upload-policy", response_model=UploadPolicy,
    dependencies=[Depends(require_filesystem_identity)],
)
async def get_upload_policy(
    parent_id: UUID, caller: Caller, content: Content, max_bytes: UploadLimit,
) -> UploadPolicy:
    with filesystem_errors():
        await content.authorize_upload(caller, parent_id)
    return UploadPolicy(max_bytes=max_bytes)


@router.post(
    "/nodes/{parent_id}/files", response_model=NodeSummary, status_code=201,
    responses=UPLOAD_RESPONSES, openapi_extra=UPLOAD_CONTRACT,
    dependencies=[Depends(require_filesystem_identity)],
)
async def upload_new_file(
    parent_id: UUID, request: Request, caller: Caller, content: Content, max_bytes: UploadLimit,
) -> NodeSummary:
    return await upload_file(request, caller, parent_id, content, max_bytes)


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


router.include_router(planned_router)
