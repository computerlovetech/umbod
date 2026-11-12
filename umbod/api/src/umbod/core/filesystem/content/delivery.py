from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import ContentRef, NodeMetadata


class ExternalDownloadRequest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    content: ContentRef
    name: str
    metadata: NodeMetadata


class ExternalDownloadInstructions(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    url: str = Field(min_length=1, repr=False)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment
            or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("Invalid download URL")
        return value


@runtime_checkable
class ExternalDownloadTransfer(Protocol):
    async def prepare_download(self, request: ExternalDownloadRequest) -> ExternalDownloadInstructions: ...
