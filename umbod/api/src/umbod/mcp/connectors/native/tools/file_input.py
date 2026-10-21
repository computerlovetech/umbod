import base64
import binascii
import re
from pathlib import PurePath
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from umbod_sdk.connectors.uploaded_file import UploadedFile, create_uploaded_file

ALLOWED_FILE_MEDIA_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
)
DEFAULT_MAXIMUM_UPLOADED_FILE_BYTES = 10 * 1024 * 1024
_SAFE_FILENAME_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]+$")


class UploadedFileWirePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=255)
    type: str
    size: int = Field(gt=0)
    data: str = Field(min_length=1)


class UploadedFilePayloadConverter(Protocol):
    def convert(self, payload: UploadedFileWirePayload) -> UploadedFile: ...


class StrictUploadedFilePayloadAdapter:
    def __init__(self, maximum_bytes: int) -> None:
        if maximum_bytes <= 0:
            raise ValueError("maximum uploaded file size must be positive")
        self._maximum_bytes = maximum_bytes

    def convert(self, payload: UploadedFileWirePayload) -> UploadedFile:
        filename = self._safe_filename(payload.name)
        if payload.type not in ALLOWED_FILE_MEDIA_TYPES:
            raise ValueError("File media type is not supported")
        if self._decoded_length(payload.data) > self._maximum_bytes:
            raise ValueError("File exceeds the maximum allowed size")
        try:
            data = base64.b64decode(payload.data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("File data is not valid base64") from error
        if not data:
            raise ValueError("Empty files are not supported")
        if len(data) > self._maximum_bytes:
            raise ValueError("File exceeds the maximum allowed size")
        if len(data) != payload.size:
            raise ValueError("Declared file size does not match file data")
        if not _matches_signature(payload.type, data):
            raise ValueError("File content does not match its declared media type")
        return create_uploaded_file(filename, payload.type, data)

    def _safe_filename(self, supplied_name: str) -> str:
        normalized = supplied_name.replace("\\", "/")
        filename = PurePath(normalized).name
        if filename != supplied_name or filename in {".", ".."}:
            raise ValueError("File name must be a safe basename")
        if len(filename) > 255 or not _SAFE_FILENAME_PATTERN.fullmatch(filename):
            raise ValueError("File name must be a safe basename of at most 255 characters")
        return filename

    def _decoded_length(self, encoded: str) -> int:
        encoded_length = len(encoded)
        if encoded_length % 4 != 0:
            raise ValueError("File data is not valid base64")
        padding = len(encoded) - len(encoded.rstrip("="))
        if padding > 2:
            raise ValueError("File data is not valid base64")
        decoded_length = encoded_length // 4 * 3 - padding
        if decoded_length > self._maximum_bytes:
            raise ValueError("File exceeds the maximum allowed size")
        return decoded_length


def _matches_signature(media_type: str, data: bytes) -> bool:
    if media_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if media_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if media_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if media_type == "image/webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return False


def uploaded_file_parameter_name(operation: object) -> str | None:
    from inspect import signature
    from typing import Annotated, get_args, get_origin

    for parameter in signature(operation).parameters.values():
        annotation = parameter.annotation
        if get_origin(annotation) is Annotated:
            annotation = get_args(annotation)[0]
        if annotation is UploadedFile:
            return parameter.name
    return None
