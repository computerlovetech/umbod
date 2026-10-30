from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_READ_BYTES = 1_048_576
MAX_READ_BASE64_CHARACTERS = 4 * ((MAX_READ_BYTES + 2) // 3)


class ReadFileCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID
    encoding: Literal["utf-8", "base64"]
    max_bytes: int = Field(
        ge=0, le=MAX_READ_BYTES,
        description="Maximum raw file bytes to return, up to 1048576; zero permits empty files only. Oversize reads fail without truncation.",
    )


class Utf8ReadContent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    encoding: Literal["utf-8"]
    text: str = Field(max_length=MAX_READ_BYTES)


class Base64ReadContent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    encoding: Literal["base64"]
    data: str = Field(max_length=MAX_READ_BASE64_CHARACTERS)


ReadContent = Annotated[Utf8ReadContent | Base64ReadContent, Field(discriminator="encoding")]


class ReadFileResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: UUID
    revision: int = Field(ge=1)
    size_bytes: int = Field(ge=0, le=MAX_READ_BYTES)
    content: ReadContent
