from typing import Any

from fastapi import HTTPException, UploadFile, status

from umbod.core.connectors.openapi.importing import (
    JsonDocumentDecodeError,
    JsonDocumentErrorCode,
    decode_json_object,
)


async def read_json_object(file: UploadFile | str, max_bytes: int) -> dict[str, Any]:
    upload = _validate_json_upload(file)
    content = await _read_bounded_content(upload, max_bytes)
    return decode_json_request_object(content)


def _validate_json_upload(file: UploadFile | str) -> UploadFile:
    if isinstance(file, str):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "openapi_import_invalid_filename"},
        )
    filename = file.filename or ""
    if not filename or not filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "openapi_import_invalid_filename"},
        )
    if file.content_type != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "openapi_import_unsupported_media_type"},
        )
    return file


async def _read_bounded_content(file: UploadFile, max_bytes: int) -> bytes:
    content = bytearray()
    while len(content) <= max_bytes:
        chunk = await file.read(min(65_536, max_bytes + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "openapi_import_too_large", "max_bytes": max_bytes},
        )
    return bytes(content)


def decode_json_request_object(content: bytes) -> dict[str, Any]:
    error_codes = {
        JsonDocumentErrorCode.INVALID_UTF8: "openapi_import_invalid_utf8",
        JsonDocumentErrorCode.MALFORMED_JSON: "openapi_import_malformed_json",
        JsonDocumentErrorCode.TRAILING_CONTENT: "openapi_import_trailing_content",
        JsonDocumentErrorCode.OBJECT_REQUIRED: "openapi_import_json_object_required",
    }
    try:
        return decode_json_object(content)
    except JsonDocumentDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": error_codes[error.code]},
        ) from error
