from typing import Annotated

from fastapi import Depends, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from ..models import CreateNodeRequest
from .deps import not_implemented, require_filesystem_identity
from .routes import PLANNED_RESPONSES

FILE_CREATION_RESPONSES = PLANNED_RESPONSES
FILE_CREATION_CONTRACT = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/CreateNodeRequest"}},
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["file"],
                    "properties": {
                        "name": {"type": "string"},
                        "metadata": {"$ref": "#/components/schemas/FilesystemNodeMetadata"},
                        "file": {"type": "string", "format": "binary"},
                    },
                },
                "encoding": {"metadata": {"contentType": "application/json"}},
            },
        },
        "description": "JSON empty creation is legacy compatibility only. Multipart upload is planned and always returns 501 without reading the body.",
    },
    "x-umbod-multipart-status": "planned",
}


async def parse_file_creation(
    request: Request,
    identity: Annotated[None, Depends(require_filesystem_identity)],
) -> CreateNodeRequest:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type == "multipart/form-data":
        not_implemented()
    if media_type and media_type != "application/json" and not (
        media_type.startswith("application/") and media_type.endswith("+json")
    ):
        raise RequestValidationError([{
            "type": "model_attributes_type",
            "loc": ("body",),
            "msg": "Body must be JSON.",
            "input": None,
        }])
    body = await request.body()
    try:
        return CreateNodeRequest.model_validate_json(body)
    except ValidationError as error:
        raise RequestValidationError([
            {**item, "loc": ("body", *item["loc"])} for item in error.errors(include_input=False)
        ], body=body) from None
