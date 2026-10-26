from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class FaviconHttpPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_body_bytes: int = Field(gt=0)
    max_redirects: int = Field(ge=0)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)


class FaviconHttpRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: HttpUrl


class FaviconHttpResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: HttpUrl
    status: int = Field(ge=100, le=599)
    content_type: str
    body: bytes


class FaviconHttpUnavailable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["unavailable"] = "unavailable"


FaviconHttpResult = FaviconHttpResponse | FaviconHttpUnavailable
