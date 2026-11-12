from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import FilesystemCreation
from umbod.core.filesystem.browsing import Breadcrumbs, FilesystemBrowsing
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.browsing.exploration import FilesystemBrowser

from umbod.core.filesystem.access import CallerNodeSummary
from umbod.core.filesystem.homes import HomeService

from .access import Access, CallerBrowseResult
from .deps import (
    get_filesystem_browsing, get_filesystem_caller, get_filesystem_creation, get_filesystem_homes,
    get_filesystem_content, get_filesystem_explorer, get_filesystem_browse_node_id,
    get_filesystem_download_delivery,
)
from .deletion import router as deletion_router
from .metadata import router as metadata_router
from .downloads import DOWNLOAD_RESPONSES, download_response
from .errors import filesystem_errors
from .models import ChildrenResponse, CreateNodeRequest
from .uploads import router as uploads_router
from .sharing import router as sharing_router

router = APIRouter(prefix="/filesystem", tags=["filesystem"])

Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Browsing = Annotated[FilesystemBrowsing, Depends(get_filesystem_browsing)]
Creation = Annotated[FilesystemCreation, Depends(get_filesystem_creation)]
Content = Annotated[FilesystemContent, Depends(get_filesystem_content)]


@router.get(
    "/browse", response_model=CallerBrowseResult,
    openapi_extra={"parameters": [{
        "name": "node_id", "in": "query", "required": False,
        "description": "Node to browse; omit to browse the filesystem root.",
        "schema": {"type": "string", "format": "uuid"},
    }]},
)
async def browse(
    caller: Caller,
    explorer: Annotated[FilesystemBrowser, Depends(get_filesystem_explorer)],
    node_id: Annotated[UUID, Depends(get_filesystem_browse_node_id)],
    access: Access,
) -> CallerBrowseResult:
    with filesystem_errors():
        result = await explorer.browse_node(caller, node_id)
        nodes = await access.enrich_nodes(caller, [result.node, *result.entries])
        return CallerBrowseResult(
            **result.model_dump(exclude={"node", "entries"}), node=nodes[0], entries=nodes[1:],
        )


@router.get("/nodes/{node_id}", response_model=CallerNodeSummary)
async def get_node(node_id: UUID, caller: Caller, browsing: Browsing, response: Response, access: Access) -> CallerNodeSummary:
    with filesystem_errors():
        node = await browsing.get_node(caller, node_id)
    response.headers["ETag"] = f'"{node.revision}"'
    with filesystem_errors():
        return (await access.enrich_nodes(caller, [node]))[0]


@router.get("/nodes/{node_id}/breadcrumbs", response_model=Breadcrumbs)
async def get_breadcrumbs(node_id: UUID, caller: Caller, browsing: Browsing) -> Breadcrumbs:
    with filesystem_errors():
        return await browsing.get_breadcrumbs(caller, node_id)


@router.get("/nodes/{parent_id}/children", response_model=ChildrenResponse)
async def list_children(parent_id: UUID, caller: Caller, browsing: Browsing, access: Access) -> ChildrenResponse:
    with filesystem_errors():
        return ChildrenResponse(nodes=await access.enrich_nodes(caller, await browsing.list_children(caller, parent_id)))


@router.get(
    "/nodes/{node_id}/content", response_class=StreamingResponse, responses=DOWNLOAD_RESPONSES,
    openapi_extra={"parameters": [{
        "name": "delivery", "in": "query", "required": False,
        "description": "Use auto for storage redirects when available, or stream for authorized API-proxied content.",
        "schema": {"type": "string", "enum": ["auto", "stream"], "default": "auto"},
    }]},
)
async def get_content(
    node_id: UUID, caller: Caller, content: Content,
    delivery: Annotated[Literal["auto", "stream"], Depends(get_filesystem_download_delivery)],
) -> Response:
    with filesystem_errors():
        download = (
            await content.open_download(caller, node_id)
            if delivery == "stream" else await content.prepare_download(caller, node_id)
        )
    return await download_response(download)


@router.post("/nodes/{parent_id}/directories", response_model=CallerNodeSummary, status_code=201)
async def create_directory(
    parent_id: UUID, body: CreateNodeRequest, caller: Caller, creation: Creation, access: Access,
) -> CallerNodeSummary:
    with filesystem_errors():
        node = await creation.create_directory(caller, parent_id, body.name, body.metadata.to_core_metadata())
        return (await access.enrich_nodes(caller, [node]))[0]


@router.post("/home", response_model=CallerNodeSummary)
async def home(
    caller: Caller, response: Response, access: Access,
    homes: Annotated[HomeService, Depends(get_filesystem_homes)],
) -> CallerNodeSummary:
    with filesystem_errors():
        node = await homes.get_or_provision(caller)
        result = (await access.enrich_nodes(caller, [node]))[0]
    response.headers["Cache-Control"] = "no-store"
    return result


router.include_router(sharing_router)
router.include_router(deletion_router)
router.include_router(metadata_router)
router.include_router(uploads_router)
