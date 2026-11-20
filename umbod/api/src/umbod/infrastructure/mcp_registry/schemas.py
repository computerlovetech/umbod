from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_validator


def _null_to_empty_text(value: object) -> object:
    return "" if value is None else value


def _null_to_empty_object(value: object) -> object:
    return {} if value is None else value


OptionalWireText = Annotated[str, BeforeValidator(_null_to_empty_text)]


class RegistryHeader(BaseModel):
    name: str
    required: bool = Field(default=False, alias="isRequired")


class RegistryRemote(BaseModel):
    type: str
    url: OptionalWireText = ""
    headers: tuple[RegistryHeader, ...] = ()

    @field_validator("headers", mode="before")
    @classmethod
    def _normalize_headers(cls, value: object) -> object:
        return () if value is None else value


class RegistryServerRecord(BaseModel):
    name: str
    title: OptionalWireText = ""
    description: str
    version: str
    remotes: tuple[RegistryRemote, ...] = ()

    @field_validator("remotes", mode="before")
    @classmethod
    def _normalize_remotes(cls, value: object) -> object:
        return () if value is None else value


class RegistryOfficialMetadata(BaseModel):
    status: str = "unknown"

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: object) -> object:
        return "unknown" if value is None else value


class RegistryListingMetadata(BaseModel):
    official: Annotated[
        RegistryOfficialMetadata, BeforeValidator(_null_to_empty_object)
    ] = Field(
        default_factory=RegistryOfficialMetadata,
        alias="io.modelcontextprotocol.registry/official",
    )


class RegistryListing(BaseModel):
    server: RegistryServerRecord
    metadata: Annotated[
        RegistryListingMetadata, BeforeValidator(_null_to_empty_object)
    ] = Field(default_factory=RegistryListingMetadata, alias="_meta")


class RegistryPageMetadata(BaseModel):
    next_cursor: OptionalWireText = Field(default="", alias="nextCursor")


class RegistrySearchResponse(BaseModel):
    servers: tuple[RegistryListing, ...]
    metadata: RegistryPageMetadata
