import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from umbod.core.filesystem import NodeMetadata
from umbod.core.filesystem.browsing import NodeSummary


HTTP_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


def validate_header_value(value: str) -> str:
    value.encode("latin-1")
    if any(ord(character) < 32 and character != "\t" or ord(character) == 127 for character in value):
        raise ValueError("Invalid HTTP header value")
    return value


class FilesystemNodeMetadata(NodeMetadata):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_core_metadata(self) -> NodeMetadata:
        return NodeMetadata(content_type=self.content_type, attributes=self.attributes)


class CreateNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    metadata: FilesystemNodeMetadata


class BeginUploadRequest(CreateNodeRequest):
    size_bytes: int = Field(ge=0, strict=True)

    @field_validator("metadata")
    @classmethod
    def validate_content_type(cls, metadata: FilesystemNodeMetadata) -> FilesystemNodeMetadata:
        content_type = metadata.content_type
        if isinstance(content_type, str):
            validate_header_value(content_type)
            media_type = content_type.split(";", 1)[0]
            parts = media_type.split("/")
            if content_type != content_type.strip() or len(parts) != 2 or not all(
                HTTP_TOKEN.fullmatch(part) for part in parts
            ):
                raise ValueError("Invalid upload content type")
        return metadata


class SameOriginAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["same_origin"] = "same_origin"


class SingleUploadTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["single"] = "single"
    method: Literal["PUT"] = "PUT"
    url: str
    headers: dict[str, str]
    authorization: SameOriginAuthorization

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        for name, value in headers.items():
            if not HTTP_TOKEN.fullmatch(name):
                raise ValueError("Invalid HTTP header name")
            validate_header_value(value)
        return headers


class UploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    expires_at: datetime
    status: Literal["pending", "uploaded", "completed"]
    transfer: SingleUploadTransfer
    complete_url: str


class ChildrenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: list[NodeSummary]
