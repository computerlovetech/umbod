from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class TelemetrySignal(str, Enum):
    LOGS = "logs"
    METRICS = "metrics"
    TRACES = "traces"


class TelemetryExport(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal: TelemetrySignal
    payload: dict[str, JsonValue]
    item_count: int = Field(ge=0)
