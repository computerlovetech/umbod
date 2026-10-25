from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdapterConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LocalAdapterConfig(AdapterConfig):
    directory: Path

    @field_validator("directory", mode="before")
    @classmethod
    def reject_empty_directory(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Local storage directory must not be empty")
        return value


class InMemoryContentConfig(AdapterConfig):
    type: Literal["inmemory"]


class LocalContentConfig(LocalAdapterConfig):
    type: Literal["local"]


ContentConfig = Annotated[
    Union[InMemoryContentConfig, LocalContentConfig],
    Field(discriminator="type"),
]


class FilesystemConfig(AdapterConfig):
    content: ContentConfig
