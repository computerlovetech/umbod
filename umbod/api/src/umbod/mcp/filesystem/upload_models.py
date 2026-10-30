import base64
import binascii
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from umbod.core.filesystem.content.errors import UploadTooLarge

from .models import FilesystemNodeMetadata

MAX_UPLOAD_BYTES = 10_485_760
MAX_BASE64_CHARACTERS = 4 * ((MAX_UPLOAD_BYTES + 2) // 3)


class Utf8Content(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    encoding: Literal["utf-8"]
    text: str = Field(
        max_length=MAX_UPLOAD_BYTES,
        description="At most 10485760 characters and 10485760 UTF-8 bytes; lower server limits apply.",
    )

    @field_validator("text", mode="before")
    @classmethod
    def bound_text(cls, value: object) -> object:
        if isinstance(value, str) and len(value) > MAX_UPLOAD_BYTES:
            raise UploadTooLarge()
        return value

    def decode(self) -> bytes:
        return self.text.encode("utf-8", errors="strict")


class Base64Content(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    encoding: Literal["base64"]
    data: str = Field(
        max_length=MAX_BASE64_CHARACTERS,
        description="At most 13981016 characters of canonical padded base64, decoding to at most 10485760 bytes.",
    )

    @field_validator("data", mode="before")
    @classmethod
    def bound_data(cls, value: object) -> object:
        if isinstance(value, str) and len(value) > MAX_BASE64_CHARACTERS:
            raise UploadTooLarge()
        return value

    def decode(self) -> bytes:
        try:
            decoded = base64.b64decode(self.data, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid base64 content") from None
        if base64.b64encode(decoded).decode("ascii") != self.data:
            raise ValueError("Invalid base64 content")
        return decoded


class UploadCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    parent_id: UUID
    name: str
    metadata: FilesystemNodeMetadata
    content: Annotated[Utf8Content | Base64Content, Field(discriminator="encoding")]
