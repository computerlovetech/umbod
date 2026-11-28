from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field

from umbod.proxies import Model


class AvailableTelemetrySetup(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["available"]
    logs_endpoint: str


class UnavailableTelemetrySetup(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unavailable"]
    reason: Literal["disabled", "not_configured"]


TelemetrySetup = Annotated[
    Union[AvailableTelemetrySetup, UnavailableTelemetrySetup],
    Field(discriminator="status"),
]
