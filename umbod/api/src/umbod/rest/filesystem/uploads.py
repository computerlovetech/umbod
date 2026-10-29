from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.uploads import UploadService, UploadSession

from .deps import get_filesystem_caller, get_filesystem_uploads, require_filesystem_identity
from .errors import filesystem_errors
from .models import (
    BeginUploadRequest, SameOriginAuthorization, SingleUploadTransfer, UploadResponse,
)

UPLOAD_RESPONSES = {
    403: {"description": "Filesystem access denied."},
    409: {"description": "Upload state, name or parent conflict."},
    410: {"description": "Incomplete upload expired."},
    413: {"description": "Upload exceeds declared or configured size."},
    415: {"description": "Content type does not match upload metadata."},
    422: {"description": "Invalid upload or shorter than declared size."},
}
router = APIRouter(dependencies=[Depends(require_filesystem_identity)])
Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Uploads = Annotated[UploadService, Depends(get_filesystem_uploads)]


def upload_response(request: Request, upload: UploadSession) -> UploadResponse:
    base = request.url.path.split("/filesystem", 1)[0] + "/filesystem/uploads/" + str(upload.id)
    content_type = upload.metadata.content_type
    return UploadResponse(
        id=upload.id, expires_at=upload.expires_at, status=upload.progress.status,
        transfer=SingleUploadTransfer(
            url=base + "/content",
            headers={"Content-Type": content_type if isinstance(content_type, str) else "application/octet-stream"},
            authorization=SameOriginAuthorization(),
        ),
        complete_url=base + "/complete",
    )


@router.options("/nodes/{parent_id}/uploads", status_code=204, responses=UPLOAD_RESPONSES)
async def upload_options(parent_id: UUID, caller: Caller, uploads: Uploads) -> Response:
    with filesystem_errors():
        await uploads.authorize_begin(caller, parent_id)
    return Response(status_code=204, headers={"Allow": "POST, OPTIONS"})


@router.post(
    "/nodes/{parent_id}/uploads", response_model=UploadResponse, status_code=201,
    responses=UPLOAD_RESPONSES,
)
async def begin_upload(
    parent_id: UUID, body: BeginUploadRequest, request: Request, response: Response,
    caller: Caller, uploads: Uploads,
) -> UploadResponse:
    with filesystem_errors():
        upload = await uploads.begin(
            caller, parent_id, body.name, body.metadata.to_core_metadata(), body.size_bytes,
        )
    result = upload_response(request, upload)
    response.headers["Location"] = result.complete_url.removesuffix("/complete")
    return result


@router.get("/uploads/{upload_id}", response_model=UploadResponse, responses=UPLOAD_RESPONSES)
async def get_upload(
    upload_id: UUID, request: Request, caller: Caller, uploads: Uploads,
) -> UploadResponse:
    with filesystem_errors():
        return upload_response(request, await uploads.get(caller, upload_id))


@router.put(
    "/uploads/{upload_id}/content", status_code=204, responses=UPLOAD_RESPONSES,
    openapi_extra={"requestBody": {"required": True, "content": {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
    }}},
)
async def put_upload_content(
    upload_id: UUID, request: Request, caller: Caller, uploads: Uploads,
) -> Response:
    with filesystem_errors():
        await uploads.put(caller, upload_id, request.headers.get("content-type", ""), request.stream())
    return Response(status_code=204)


@router.post(
    "/uploads/{upload_id}/complete", response_model=NodeSummary, status_code=201,
    responses={**UPLOAD_RESPONSES, 200: {"model": NodeSummary, "description": "Already completed."}},
)
async def complete_upload(
    upload_id: UUID, request: Request, response: Response, caller: Caller, uploads: Uploads,
) -> NodeSummary:
    with filesystem_errors():
        result = await uploads.complete(caller, upload_id)
    response.status_code = 201 if result.created else 200
    base = request.url.path.split("/filesystem", 1)[0] + "/filesystem/nodes/"
    response.headers["Location"] = base + str(result.node.id)
    return result.node
