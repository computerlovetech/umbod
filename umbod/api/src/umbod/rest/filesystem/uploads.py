from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import FormData, UploadFile

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.content import FilesystemContent

from .errors import filesystem_errors
from .models import CreateNodeRequest, FilesystemNodeMetadata
from .multipart import BoundedMultipartParser, MULTIPART_ERRORS, UploadLimitExceeded

UPLOAD_RESPONSES = {
    403: {"description": "Filesystem access denied."},
    409: {"description": "Name already exists or parent is not a directory."},
    413: {"description": "File or multipart request exceeds the configured limit."},
    415: {"description": "File uploads require multipart/form-data."},
    422: {"description": "Invalid name, metadata or multipart request."},
}
UPLOAD_CONTRACT = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object", "additionalProperties": False, "required": ["file"],
                    "properties": {
                        "name": {"type": "string"},
                        "metadata": {"$ref": "#/components/schemas/FilesystemNodeMetadata"},
                        "file": {"type": "string", "format": "binary"},
                    },
                },
                "encoding": {"metadata": {"contentType": "application/json"}},
            },
        },
        "description": "Upload one file with multipart. Omitted name uses the uploaded filename. Omitted metadata uses the part content type and empty attributes. Names are never overwritten. Zero-byte uploads are allowed.",
    },
}


def invalid_upload() -> HTTPException:
    return HTTPException(422, detail={
        "code": "filesystem_invalid_upload", "message": "Invalid multipart file upload.",
    })


def upload_fields(form: FormData) -> tuple[UploadFile, CreateNodeRequest]:
    items = form.multi_items()
    names = [name for name, _ in items]
    if len(names) != len(set(names)) or set(names) - {"file", "name", "metadata"}:
        raise invalid_upload()
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise invalid_upload()
    name = form.get("name", file.filename)
    metadata = form.get("metadata")
    if not isinstance(name, str) or (metadata is not None and not isinstance(metadata, str)):
        raise invalid_upload()
    try:
        parsed_metadata = (
            FilesystemNodeMetadata.model_validate_json(metadata)
            if isinstance(metadata, str) else FilesystemNodeMetadata(
                content_type=file.content_type or "application/octet-stream", attributes={},
            )
        )
        body = CreateNodeRequest(name=name, metadata=parsed_metadata)
    except ValidationError:
        raise invalid_upload() from None
    return file, body


async def file_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await file.read(65_536):
        yield chunk


async def upload_file(
    request: Request, caller: CallerSnapshot, parent_id: UUID,
    content: FilesystemContent, max_bytes: int,
) -> NodeSummary:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "multipart/form-data":
        raise HTTPException(415, detail={
            "code": "filesystem_upload_media_type", "message": "File uploads require multipart/form-data.",
        })
    with filesystem_errors():
        await content.authorize_upload(caller, parent_id)
    try:
        form = await BoundedMultipartParser(request, max_bytes).parse()
    except UploadLimitExceeded:
        raise HTTPException(413, detail={
            "code": "filesystem_upload_too_large", "message": "Upload exceeds the configured size limit.",
            "max_bytes": max_bytes,
        }) from None
    except MULTIPART_ERRORS:
        raise invalid_upload() from None
    try:
        file, body = upload_fields(form)
        with filesystem_errors():
            return await content.upload(
                caller, parent_id, body.name, body.metadata.to_core_metadata(), file_chunks(file),
            )
    finally:
        await form.close()
