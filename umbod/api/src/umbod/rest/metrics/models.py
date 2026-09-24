from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat


class RestMetricSample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    labels: Mapping[str, str]
    value: float


class CompletedRestRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str = Field(min_length=1, pattern=r"^[A-Z]+$")
    normalized_route: str = Field(min_length=1, pattern=r"^/[^?#]*$")
    status_class: Literal["1xx", "2xx", "3xx", "4xx", "5xx"]
    duration_seconds: PositiveFloat
