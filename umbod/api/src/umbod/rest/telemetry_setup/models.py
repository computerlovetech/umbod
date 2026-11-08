from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class AvailableTelemetrySetup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["available"]
    logs_endpoint: str


class UnavailableTelemetrySetup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unavailable"]
    reason: Literal["disabled", "not_configured"]


TelemetrySetup = Annotated[
    Union[AvailableTelemetrySetup, UnavailableTelemetrySetup],
    Field(discriminator="status"),
]
