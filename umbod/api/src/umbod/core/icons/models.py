from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator


class Favicon(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    mime_type: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if value.startswith("data:image/") and "," in value:
            return value
        url = TypeAdapter(HttpUrl).validate_python(value)
        if url.username is not None or url.password is not None:
            raise ValueError("Icon URLs must not contain credentials")
        return value


class FaviconDiscoveryRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_url: HttpUrl
    advertised_icons: tuple[Favicon, ...]

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("Endpoint URLs must not contain credentials")
        return value


class FaviconFound(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["found"] = "found"
    icon: Favicon
    strategy: str


class FaviconNotFound(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["not_found"] = "not_found"


class FaviconDiscoveryTimedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["timed_out"] = "timed_out"


FaviconDiscoveryResult = Annotated[
    FaviconFound | FaviconNotFound | FaviconDiscoveryTimedOut,
    Field(discriminator="status"),
]
