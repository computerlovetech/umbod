from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from umbod.core.filesystem.uploads import UploadService

from .deps import get_filesystem_uploads
from .errors import filesystem_errors


router = APIRouter()


@router.put("/uploads/{upload_id}/transfer", status_code=204)
async def transfer_upload(
    upload_id: UUID, request: Request,
    uploads: Annotated[UploadService, Depends(get_filesystem_uploads)],
) -> Response:
    try:
        with filesystem_errors():
            await uploads.put_delegated(
                upload_id, request.headers.get("x-umbod-upload-token", ""),
                request.headers.get("content-type", ""), request.stream(),
            )
    except HTTPException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
