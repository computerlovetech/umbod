import ipaddress
import re
from pathlib import Path
from typing import Annotated, Literal, Union
from unicodedata import category
from urllib.parse import urlsplit

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


class S3ContentConfig(AdapterConfig):
    type: Literal["s3"]
    bucket: str
    region: str
    endpoint_url: str
    prefix: str
    addressing_style: Literal["auto", "virtual", "path"]

    @field_validator("bucket")
    @classmethod
    def validate_bucket(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", value):
            raise ValueError("Invalid S3 bucket name")
        if ".." in value or ".-" in value or "-." in value:
            raise ValueError("Invalid S3 bucket name")
        if value.startswith(("xn--", "sthree-", "amzn-s3-demo-")) or value.endswith(
            ("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3")
        ):
            raise ValueError("Unsupported S3 bucket name")
        try:
            ipaddress.ip_address(value)
        except ValueError:
            return value
        raise ValueError("Invalid S3 bucket name")

    @field_validator("region")
    @classmethod
    def validate_region(cls, value: str) -> str:
        if not value.strip() or value != value.strip() or any(c.isspace() for c in value):
            raise ValueError("Invalid S3 region")
        return value

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        if value == "":
            return value
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in ("http", "https") and parsed.hostname
                and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment and "?" not in value and "#" not in value
                and not any(c.isspace() or category(c) == "Cc" for c in value)
                and "\\" not in value
            )
            parsed.port
        except ValueError:
            raise ValueError("Invalid S3 endpoint") from None
        if not valid:
            raise ValueError("Invalid S3 endpoint")
        return value

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if value == "":
            return value
        if (
            any(segment in ("", ".", "..") for segment in value.split("/"))
            or "\\" in value
            or any(category(c) == "Cc" for c in value)
            or len(value.encode("utf-8")) > 991
        ):
            raise ValueError("Invalid S3 prefix")
        return value


ContentConfig = Annotated[
    Union[InMemoryContentConfig, LocalContentConfig, S3ContentConfig],
    Field(discriminator="type"),
]


class FilesystemConfig(AdapterConfig):
    content: ContentConfig
